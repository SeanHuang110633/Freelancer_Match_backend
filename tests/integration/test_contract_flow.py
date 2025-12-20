import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.contract import Contract
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
    
    測試場景：
    1. [Employer] 刊登案件 (Create Project)
    2. [Freelancer] 提交提案 (Submit Proposal) + 檔案上傳
    3. [Employer] 接受提案 (Accept Proposal)
    4. [Employer] 建立合約草稿 (Create Contract Draft)
    5. [Freelancer] 同意合約 (Sign Contract) -> 狀態轉為「進行中」
    6. [System] 驗證案件狀態自動轉為「已成案」
    """

    # ==========================================
    # 1. [Employer] 刊登案件
    # ==========================================
    project_payload = {
        "title": "Website Redesign 2024",
        "description": "Need a modern look using Vue 3",
        "budget_min": 10000,
        "work_type": "遠端",
        "skill_tag_ids": [] # 測試簡化，不傳標籤
    }
    
    resp_proj = await client.post(
        "/projects/", 
        json=project_payload, 
        headers=employer_auth_headers
    )
    
    assert resp_proj.status_code == 201, f"刊登案件失敗: {resp_proj.text}"
    project_data = resp_proj.json()
    project_id = project_data["project_id"]
    assert project_data["status"] == "招募中"

    # ==========================================
    # 2. [Freelancer] 提交提案 (含檔案)
    # ==========================================
    # 模擬 PDF 檔案上傳
    # 格式: (filename, file_content, content_type)
    files = {
        "attachment": ("proposal.pdf", b"%PDF-1.4 mock content...", "application/pdf")
    }
    # Form Data 欄位
    form_data = {
        "brief_description": "I have extensive experience with Vue 3."
    }
    
    resp_prop = await client.post(
        f"/projects/{project_id}/proposals",
        data=form_data, # Form fields
        files=files,    # Multipart file
        headers=freelancer_auth_headers
    )
    
    assert resp_prop.status_code == 201, f"提交提案失敗: {resp_prop.text}"
    proposal_data = resp_prop.json()
    proposal_id = proposal_data["proposal_id"]
    
    # 驗證 DB 有寫入檔案路徑 (Local Storage 模式下會包含 /static/uploads)
    assert proposal_data["attachment_url"] is not None
    assert "proposal.pdf" in proposal_data["attachment_url"] or ".pdf" in proposal_data["attachment_url"]

    # ==========================================
    # 3. [Employer] 接受提案
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
    # 4. [Employer] 建立合約草稿
    # ==========================================
    # 根據需求 M7.1，以提案 ID 自動產生合約
    resp_contract = await client.post(
        "/contracts/",
        json={"proposal_id": proposal_id},
        headers=employer_auth_headers
    )
    
    assert resp_contract.status_code == 201, f"建立合約失敗: {resp_contract.text}"
    contract_data = resp_contract.json()
    contract_id = contract_data["contract_id"]
    
    # 驗證合約初始狀態與資料繼承
    assert contract_data["status"] == "協商中"
    assert contract_data["title"] == project_payload["title"]
    
    # 驗證關聯資料 (Eager Loading 檢查)
    # 檢查是否正確回傳了雇主與工作者的巢狀結構
    assert "employer" in contract_data
    assert "freelancer" in contract_data
    assert "freelancer_profile" in contract_data["freelancer"]

    # ==========================================
    # 5. [Freelancer] 同意合約 -> 狀態轉為「進行中」
    # ==========================================
    # 根據狀態機： ("協商中", "進行中") 允許由「自由工作者」執行
    
    resp_sign = await client.patch(
        f"/contracts/{contract_id}/status",
        json={"status": "進行中"},
        headers=freelancer_auth_headers
    )
    
    assert resp_sign.status_code == 200, f"簽署合約失敗: {resp_sign.text}"
    final_contract = resp_sign.json()
    assert final_contract["status"] == "進行中"

    # ==========================================
    # 6. [System] 最終 DB 狀態驗證
    # ==========================================
    # 驗證需求 M7.4：合約生效後，案件狀態應自動轉為「已成案」
    
    # 因為 API 和測試共用 Session，為了確保讀到最新狀態，我們重新查詢 DB
    stmt = select(Project).where(Project.project_id == project_id)
    result = await db_session.execute(stmt)
    db_project = result.scalars().first()
    
    assert db_project is not None
    # 注意：這裡驗證的是 Enum 字串值
    assert db_project.status == "已成案", f"案件狀態未連動更新，目前為: {db_project.status}"