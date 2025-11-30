import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.proposal import Proposal

@pytest.mark.asyncio
async def test_proposal_lifecycle_and_constraints(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 1】提案模組補完計畫
    
    流程：
    1. (Setup) 雇主刊登案件
    2. [Freelancer] 提交提案 (Submit)
    3. [Freelancer] 嘗試重複提交同一案件 (驗證 Constraint) -> 預期失敗
    4. [Freelancer] 查看我的提案列表 (Get My Proposals) -> 驗證資料存在
    5. [Freelancer] 修改提案內容 (Update) -> 驗證更新成功
    6. [Freelancer] 撤回提案 (Withdraw) -> 驗證刪除成功
    7. [Freelancer] 再次查看列表 -> 驗證已空
    """

    # ==========================================
    # 1. Setup: 雇主刊登案件
    # ==========================================
    project_payload = {
        "title": "Logo Design",
        "description": "Need a cool logo",
        "budget_min": 3000,
        "work_type": "遠端",
        "skill_tag_ids": []
    }
    resp_proj = await client.post(
        "/projects/", 
        json=project_payload, 
        headers=employer_auth_headers
    )
    assert resp_proj.status_code == 201
    project_id = resp_proj.json()["project_id"]

    # ==========================================
    # 2. 提交提案 (Submit)
    # ==========================================
    files = {
        "attachment": ("draft_v1.pdf", b"%PDF-1.4 content v1", "application/pdf")
    }
    data = {
        "brief_description": "First draft idea."
    }
    
    resp_submit = await client.post(
        f"/projects/{project_id}/proposals",
        data=data,
        files=files,
        headers=freelancer_auth_headers
    )
    assert resp_submit.status_code == 201
    proposal_data = resp_submit.json()
    proposal_id = proposal_data["proposal_id"]
    assert proposal_data["brief_description"] == "First draft idea."

    # ==========================================
    # 3. 驗證重複提案限制 (Duplicate Constraint)
    # ==========================================
    # 同一個工作者對同一個案件再次提案，應該被擋下 (400 Bad Request)
    resp_duplicate = await client.post(
        f"/projects/{project_id}/proposals",
        data={"brief_description": "Try again"},
        files={"attachment": ("p.pdf", b"pdf", "application/pdf")},
        headers=freelancer_auth_headers
    )
    # 根據 proposal_service.py 的邏輯，這裡會 raise HTTPException(400, "你已經對此案件提案")
    assert resp_duplicate.status_code == 400 
    assert "你已經對此案件提案" in resp_duplicate.json()["detail"]

    # ==========================================
    # 4. 查看我的提案 (Get My Proposals)
    # ==========================================
    resp_list = await client.get("/proposals/my", headers=freelancer_auth_headers)
    assert resp_list.status_code == 200
    my_proposals = resp_list.json()
    
    assert len(my_proposals) >= 1
    # 確保剛提的那筆在裡面
    target_proposal = next((p for p in my_proposals if p["proposal_id"] == proposal_id), None)
    assert target_proposal is not None
    assert target_proposal["project"]["title"] == "Logo Design" # 驗證有包含簡易案件資訊

    # ==========================================
    # 5. 修改提案 (Update Proposal)
    # ==========================================
    # 測試更新描述與重新上傳檔案
    new_files = {
        "attachment": ("draft_v2.pdf", b"%PDF-1.4 content v2", "application/pdf")
    }
    new_data = {
        "brief_description": "Updated draft idea."
    }
    
    # 呼叫 PUT /proposals/{id}
    resp_update = await client.put(
        f"/proposals/{proposal_id}",
        data=new_data,
        files=new_files,
        headers=freelancer_auth_headers
    )
    assert resp_update.status_code == 200
    updated_data = resp_update.json()
    
    assert updated_data["brief_description"] == "Updated draft idea."
    # 驗證 DB 中的檔案路徑已變更 (檔名會變因為是用 uuid 生成的)
    assert updated_data["attachment_url"] != proposal_data["attachment_url"]

    # ==========================================
    # 6. 撤回提案 (Withdraw/Delete)
    # ==========================================
    resp_delete = await client.delete(
        f"/proposals/{proposal_id}",
        headers=freelancer_auth_headers
    )
    assert resp_delete.status_code == 204 # No Content

    # ==========================================
    # 7. 驗證刪除結果
    # ==========================================
    # 再次查詢我的提案，應該找不到該筆 ID
    resp_list_after = await client.get("/proposals/my", headers=freelancer_auth_headers)
    my_proposals_after = resp_list_after.json()
    
    deleted_proposal = next((p for p in my_proposals_after if p["proposal_id"] == proposal_id), None)
    assert deleted_proposal is None

    # 雙重驗證：直接查 DB
    stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
    result = await db_session.execute(stmt)
    assert result.scalars().first() is None