import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.contract import Contract
from app.models.freelancer_profile import FreelancerProfile
from app.models.review import Review

# 為了避免每個測試都要重寫幾十行「建立合約」的程式碼，
# 我們寫一個 Helper 函式來快速將合約推到「進行中」狀態
async def setup_active_contract(client: AsyncClient, employer_headers, freelancer_headers):
    # 1. 雇主刊登案件
    resp_proj = await client.post(
        "/projects/", 
        headers=employer_headers, 
        json={"title": "Deliverable Test Job", "description": "desc", "budget_min": 5000}
    )
    project_id = resp_proj.json()["project_id"]

    # 2. 工作者提案
    files = {"attachment": ("p.pdf", b"content", "application/pdf")}
    resp_prop = await client.post(
        f"/projects/{project_id}/proposals",
        headers=freelancer_headers,
        data={"brief_description": "pick me"},
        files=files
    )
    proposal_id = resp_prop.json()["proposal_id"]

    # 3. 雇主接受 -> 建立合約
    await client.patch(f"/proposals/{proposal_id}/status", headers=employer_headers, json={"status": "已接受"})
    resp_contract = await client.post("/contracts/", headers=employer_headers, json={"proposal_id": proposal_id})
    contract_id = resp_contract.json()["contract_id"]

    # 4. 工作者簽約 -> 進行中
    await client.patch(f"/contracts/{contract_id}/status", headers=freelancer_headers, json={"status": "進行中"})
    
    return contract_id, project_id

@pytest.mark.asyncio
async def test_deliverable_and_review_flow(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 P2】交付與評價流程
    
    流程：
    1. (Setup) 快速建立一個「進行中」的合約
    2. [Freelancer] 上傳交付物 (Deliverable)
    3. [Employer]   檢視交付物
    4. [Employer]   驗收通過 -> 合約狀態變更為「已完成」
    5. [Employer]   評價工作者 (Review)
    6. [System]     驗證工作者信譽分數是否更新
    7. [Freelancer] 評價雇主 (Review)
    """
    
    # 1. Setup: 準備一個進行中的合約
    contract_id, _ = await setup_active_contract(client, employer_auth_headers, freelancer_auth_headers)

    # ==========================================
    # 2. 上傳交付物 (Upload Deliverable)
    # ==========================================
    files = {
        "file": ("final_work.zip", b"binary content", "application/zip")
    }
    data = {"description": "Here is the final work."}
    
    resp_upload = await client.post(
        f"/contracts/{contract_id}/deliverables",
        headers=freelancer_auth_headers,
        data=data,
        files=files
    )
    assert resp_upload.status_code == 201
    deliverable_data = resp_upload.json()
    assert deliverable_data["description"] == "Here is the final work."
    assert "file_url" in deliverable_data

    # ==========================================
    # 2.5 請求驗收 (Request Acceptance)
    # ==========================================
    # 根據業務邏輯，必須切換狀態，雇主才看得到交付物
    resp_req_accept = await client.patch(
        f"/contracts/{contract_id}/status",
        headers=freelancer_auth_headers,
        json={"status": "工作者要求驗收"}
    )
    assert resp_req_accept.status_code == 200
    assert resp_req_accept.json()["status"] == "工作者要求驗收"

    # ==========================================
    # 3. 檢視交付物 (List Deliverables)
    # ==========================================
    # 雇主查看列表
    resp_list = await client.get(
        f"/contracts/{contract_id}/deliverables",
        headers=employer_auth_headers
    )
    assert resp_list.status_code == 200
    items = resp_list.json()
    assert len(items) == 1
    assert items[0]["deliverable_id"] == deliverable_data["deliverable_id"]

    # ==========================================
    # 4. 驗收完成 (Complete Contract)
    # ==========================================
    # 雇主將狀態改為「已完成」 (觸發 Review 權限開啟)
    resp_complete = await client.patch(
        f"/contracts/{contract_id}/status",
        headers=employer_auth_headers,
        json={"status": "已完成"}
    )
    assert resp_complete.status_code == 200
    assert resp_complete.json()["status"] == "已完成"

    # ==========================================
    # 5. 雇主評價工作者 (Employer reviews Freelancer)
    # ==========================================
    # 測試給一個非滿分的評價，看看分數計算是否正確
    # 4 分評價
    review_payload_fw = {
        "contract_id": contract_id,
        "comment": "Good job but slightly late.",
        "rating_communication_fw": 4.0,
        "rating_professionalism_fw": 4.0,
        "rating_punctuality_fw": 4.0,
        "rating_quality_fw": 4.0
    }
    
    resp_review_fw = await client.post(
        "/reviews/",
        headers=employer_auth_headers,
        json=review_payload_fw
    )
    assert resp_review_fw.status_code == 201
    assert resp_review_fw.json()["rating_quality_fw"] == 4.0

    # ==========================================
    # 6. 驗證信譽分數 (Verify Reputation Score)
    # ==========================================
    # FreelancerProfile 的 user_id
    # 我們需要從 Auth Helper 裡面的 token 或 setup 過程中得知 user_id，
    # 但這裡最簡單的方式是直接從 DB 撈 Profile
    
    # 透過 API 獲取工作者 Profile (需要知道 ID? 或直接用 working user 登入查 /me)
    resp_me = await client.get("/profiles/me", headers=freelancer_auth_headers)
    assert resp_me.status_code == 200
    profile_data = resp_me.json()
    
    # 預設是 5.0，剛剛給了 4.0，所以現在應該要是 4.0 (因為只有一筆)
    # 注意：API 回傳的可能是 float
    assert profile_data["reputation_score"] == 4.0

    # ==========================================
    # 7. 工作者評價雇主 (Freelancer reviews Employer)
    # ==========================================
    review_payload_we = {
        "contract_id": contract_id,
        "comment": "Great client!",
        "rating_communication_we": 5.0,
        "rating_quality_we": 5.0,
        "rating_compensation_we": 5.0,
        "rating_process_we": 5.0
    }
    resp_review_we = await client.post(
        "/reviews/",
        headers=freelancer_auth_headers,
        json=review_payload_we
    )
    assert resp_review_we.status_code == 201
    
    # 驗證不能重複評價
    resp_duplicate = await client.post(
        "/reviews/",
        headers=freelancer_auth_headers,
        json=review_payload_we
    )
    assert resp_duplicate.status_code == 409 # Conflict