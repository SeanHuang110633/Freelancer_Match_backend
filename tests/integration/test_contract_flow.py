import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.contract import Contract
from app.models.proposal import Proposal
from app.models.project import Project

@pytest.mark.asyncio
async def test_full_contract_lifecycle(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 P1】提案與合約全生命週期
    
    角色：
    - Employer (雇主)
    - Freelancer (工作者)

    流程：
    1. [Employer]   刊登案件 (Project)
    2. [Freelancer] 提交提案 (Proposal) + 上傳 PDF
    3. [Employer]   接受提案 (Accept Proposal)
    4. [Employer]   建立合約草稿 (Create Contract Draft)
    5. [Freelancer] 同意合約 -> 狀態轉為「進行中」
    """

    # ==========================================
    # 1. 雇主刊登案件 (Create Project)
    # ==========================================
    project_payload = {
        "title": "Website Redesign",
        "description": "Need a modern look",
        "budget_min": 10000,
        "work_type": "遠端",
        "skill_tag_ids": [] # 簡化測試，不傳標籤
    }
    resp_proj = await client.post(
        "/projects/", 
        json=project_payload, 
        headers=employer_auth_headers
    )
    assert resp_proj.status_code == 201
    project_id = resp_proj.json()["project_id"]

    # ==========================================
    # 2. 工作者提交提案 (Submit Proposal)
    # ==========================================
    # 模擬檔案上傳 (multipart/form-data)
    # 注意：這裡的 key 'attachment' 必須對應 router 中的 File(alias="attachment") 或參數名稱
    files = {
        "attachment": ("proposal.pdf", b"%PDF-1.4 mock content", "application/pdf")
    }
    data = {
        "brief_description": "I am the best fit for this job."
    }
    
    resp_prop = await client.post(
        f"/projects/{project_id}/proposals",
        data=data,   # Form fields
        files=files, # File upload
        headers=freelancer_auth_headers
    )
    assert resp_prop.status_code == 201
    proposal_data = resp_prop.json()
    proposal_id = proposal_data["proposal_id"]
    
    # 驗證 DB 有寫入檔案路徑 (Local Storage 模式)
    assert proposal_data["attachment_url"] is not None
    assert "/static/uploads/proposals/" in proposal_data["attachment_url"]

    # ==========================================
    # 3. 雇主接受提案 (Accept Proposal)
    # ==========================================
    # 呼叫 PATCH /proposals/{id}/status
    resp_accept = await client.patch(
        f"/proposals/{proposal_id}/status",
        json={"status": "已接受"},
        headers=employer_auth_headers
    )
    assert resp_accept.status_code == 200
    assert resp_accept.json()["status"] == "已接受"

    # ==========================================
    # 4. 雇主建立合約 (Create Contract)
    # ==========================================
    # 根據需求 7.1，以提案 ID 自動產生合約
    resp_contract = await client.post(
        "/contracts/",
        json={"proposal_id": proposal_id},
        headers=employer_auth_headers
    )
    assert resp_contract.status_code == 201
    contract_data = resp_contract.json()
    contract_id = contract_data["contract_id"]
    
    # 驗證合約初始狀態
    assert contract_data["status"] == "協商中"
    assert contract_data["title"] == "Website Redesign" # 繼承案件標題
    
    # 驗證關聯是否正確 (Eager Loading check)
    assert contract_data["employer"]["email"] == "integration_employer@example.com"
    assert contract_data["freelancer"]["freelancer_profile"] is not None 
    # (如果 freelancer 還沒建 profile，這裡可能是 null，視 conftest 設定而定，
    # 但 freelancer key 本身必須存在)

    # ==========================================
    # 5. 狀態流轉：工作者同意 -> 進行中
    # ==========================================
    # 根據 ContractService 的狀態機邏輯：
    # ("協商中", "進行中"): ["自由工作者"] (工作者同意)
    
    resp_sign = await client.patch(
        f"/contracts/{contract_id}/status",
        json={"status": "進行中"},
        headers=freelancer_auth_headers
    )
    
    assert resp_sign.status_code == 200
    assert resp_sign.json()["status"] == "進行中"

    # ==========================================
    # 6. 最終 DB 狀態驗證
    # ==========================================
    # 再次確認案件狀態是否連動更新為 "已成案" (M7.4 需求)
    stmt = select(Project).where(Project.project_id == project_id)
    result = await db_session.execute(stmt)
    db_project = result.scalars().first()
    
    assert db_project.status == "已成案"