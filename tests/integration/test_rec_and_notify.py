import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.skill_tag import SkillTag
from app.models.notification import Notification
from app.models.review import Review
from app.models.contract import Contract
from app.models.project import Project
from datetime import datetime
import uuid

@pytest.mark.asyncio
async def test_recommendation_system(
    client: AsyncClient,
    freelancer_auth_headers: dict,
    employer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 3-1】推薦系統驗證
    情境：
    1. 建立技能 "Python"
    2. 工作者設定技能 "Python"
    3. 雇主刊登需要 "Python" 的案件
    4. 工作者呼叫推薦 API -> 應該看到該案件
    """
    # 1. Setup: 建立技能
    tag_python = SkillTag(name="Python-Rec", category="Backend")
    db_session.add(tag_python)
    await db_session.flush()
    
    # 2. Freelancer 設定技能
    await client.put(
        "/profiles/freelancer/skills",
        json={"skill_tag_ids": [tag_python.tag_id]},
        headers=freelancer_auth_headers
    )

    # 3. Employer 刊登案件 (需要 Python)
    await client.post(
        "/projects/",
        headers=employer_auth_headers,
        json={
            "title": "Python Recommendation Job",
            "description": "Rec test",
            "skill_tag_ids": [tag_python.tag_id]
        }
    )

    # 4. Act: 工作者獲取推薦
    resp_rec = await client.get("/recommendations/jobs", headers=freelancer_auth_headers)
    assert resp_rec.status_code == 200
    rec_data = resp_rec.json()
    
    # 5. Assert: 驗證結果
    # 應該要包含剛剛刊登的案件，且分數大於 0
    items = rec_data["items"]
    assert len(items) >= 1
    assert items[0]["project"]["title"] == "Python Recommendation Job"
    assert items[0]["recommendation_score"] > 0

@pytest.mark.asyncio
async def test_notification_flow(
    client: AsyncClient,
    employer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 3-2】通知系統驗證 (查閱與標記)
    1. 直接在 DB 插入一筆通知給雇主
    2. 雇主呼叫列表 API -> 驗證看到通知
    3. 雇主呼叫標記已讀 API -> 驗證狀態變更
    """
    # 1. Arrange: 獲取雇主 ID 並插入通知
    resp_me = await client.get("/users/me", headers=employer_auth_headers)
    user_id = resp_me.json()["user_id"]

    note = Notification(
        user_id=user_id,
        title="Test Notification",
        message="Hello",
        link_url="/test",
        is_read=False
    )
    db_session.add(note)
    await db_session.commit() # 提交以產生 ID
    await db_session.refresh(note)
    note_id = note.notification_id

    # 2. Act: 獲取列表
    resp_list = await client.get("/notifications/my", headers=employer_auth_headers)
    assert resp_list.status_code == 200
    notes = resp_list.json()
    
    target_note = next((n for n in notes if n["notification_id"] == note_id), None)
    assert target_note is not None
    assert target_note["title"] == "Test Notification"
    assert target_note["is_read"] is False

    # 3. Act: 標記已讀
    resp_read = await client.patch(
        f"/notifications/{note_id}/read", 
        headers=employer_auth_headers
    )
    assert resp_read.status_code == 200
    assert resp_read.json()["is_read"] is True

    # 4. Double Check DB
    # 這裡需要 expire 或重新查詢以確保拿到最新狀態 (如同我們在 profile_repo 學到的)
    # 但因為我們是透過 API 觸發 update，這是新的 request，所以 DB 應該已經更新
    stmt = select(Notification).where(Notification.notification_id == note_id)
    result = await db_session.execute(stmt)
    db_note = result.scalars().first()
    assert db_note.is_read is True

@pytest.mark.asyncio
async def test_read_reviews(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 3-3】讀取評價 API
    使用 Data Seeding (直接寫入 DB) 模擬已完成的合約與評價，
    驗證 GET /reviews/contract/{id} 能正確回傳資料。
    """
    # 1. Arrange: 準備 User ID
    emp_resp = await client.get("/users/me", headers=employer_auth_headers)
    emp_id = emp_resp.json()["user_id"]
    
    free_resp = await client.get("/users/me", headers=freelancer_auth_headers)
    free_id = free_resp.json()["user_id"]

    # 2. Arrange: 準備 Project & Contract (最小化欄位即可)
    # 為了避開 foreign key 檢查，我們需要一個真實的 project_id，這裡借用 API 快速建立
    resp_proj = await client.post(
        "/projects/", 
        headers=employer_auth_headers, 
        json={"title": "Reviewed Project", "description": "desc", "budget_min": 100}
    )
    project_id = resp_proj.json()["project_id"]

    # 這裡我們必須塞一個假的 proposal_id，因為 Contract 的外鍵約束
    # 為了省事，我們可以不建 Proposal，但如果 DB 有設 foreign key constraint 就會報錯
    # 假設您的 DB schema 有嚴格約束，我們還是乖乖建一個 Proposal
    # 但為了演示 Data Seeding 的威力，我們試著直接操作 DB 物件
    
    # 建立 Proposal
    from app.models.proposal import Proposal
    proposal = Proposal(
        project_id=project_id,
        freelancer_id=free_id,
        brief_description="Seed proposal"
    )
    db_session.add(proposal)
    await db_session.flush()

    contract = Contract(
        project_id=project_id,
        proposal_id=proposal.proposal_id,
        employer_id=emp_id,
        freelancer_id=free_id,
        title="Reviewed Contract",
        content="...",
        amount=1000,
        status="已完成",
        end_date=datetime.now()
    )
    db_session.add(contract)
    await db_session.flush()
    contract_id = contract.contract_id

    # 3. Arrange: 插入評價 (Review)
    review = Review(
        contract_id=contract_id,
        reviewer_id=emp_id,
        reviewee_id=free_id,
        rating_professionalism_fw=5.0,
        rating_quality_fw=4.5,
        comment="Seeded Review Comment"
    )
    db_session.add(review)
    await db_session.commit()

    # 4. Act: 呼叫 API 讀取評價
    resp_get = await client.get(f"/reviews/contract/{contract_id}", headers=employer_auth_headers)
    
    # 5. Assert
    assert resp_get.status_code == 200
    reviews_data = resp_get.json()
    assert len(reviews_data) == 1
    assert reviews_data[0]["comment"] == "Seeded Review Comment"
    assert reviews_data[0]["rating_quality_fw"] == 4.5