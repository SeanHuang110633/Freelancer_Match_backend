import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.freelancer_profile import FreelancerProfile
from app.models.skill_tag import SkillTag

@pytest.mark.asyncio
async def test_update_profile_info(
    client: AsyncClient,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 2-1】基本資料更新驗證
    驗證使用者能透過 API 修改自己的個人簡介與公開狀態。
    """
    # 1. Arrange: 準備更新資料
    new_bio = "Updated Bio: I am a full-stack expert."
    update_payload = {
        "full_name": "Updated Name",
        "bio": new_bio,
        "visibility": "僅受邀" # 測試 Enum 欄位
    }

    # 2. Act: 呼叫 PUT /profiles/me
    response = await client.put(
        "/profiles/me",
        json=update_payload,
        headers=freelancer_auth_headers
    )

    # 3. Assert Response
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"
    assert data["visibility"] == "僅受邀"

    # 4. Assert Database (確保資料持久化)
    # 我們需要知道 user_id，這可以從 header token 解析，或者從 API 回傳取得
    user_id = data["user_id"]
    stmt = select(FreelancerProfile).where(FreelancerProfile.user_id == user_id)
    result = await db_session.execute(stmt)
    db_profile = result.scalars().first()
    
    assert db_profile.bio == new_bio
    assert db_profile.visibility == "僅受邀"

@pytest.mark.asyncio
async def test_skill_management_and_search_flow(
    client: AsyncClient,
    freelancer_auth_headers: dict,
    employer_auth_headers: dict,
    db_session
):
    """
    【整合測試 Step 2-2】技能管理與人才搜尋流程
    
    流程：
    1. (Setup) 系統預先建立技能標籤 (Tag A, Tag B)
    2. [Freelancer] 設定自己的技能為 [Tag A, Tag B]
    3. [Freelancer] 驗證 DB 中技能關聯表是否寫入
    4. [Employer]   搜尋 Tag A -> 應該找到該 Freelancer
    5. [Employer]   搜尋 Tag C (不存在的技能) -> 應該找不到
    """

    # ==========================================
    # 1. Setup: 建立技能標籤
    # ==========================================
    tag_react = SkillTag(name="React", category="Frontend")
    tag_node = SkillTag(name="Node.js", category="Backend")
    tag_go = SkillTag(name="Go", category="Backend") # 不會被選中的技能
    db_session.add_all([tag_react, tag_node, tag_go])
    await db_session.flush() # 取得 IDs
    
    react_id = tag_react.tag_id
    node_id = tag_node.tag_id
    go_id = tag_go.tag_id

    # ==========================================
    # 2. Freelancer 設定技能 (Update Skills)
    # ==========================================
    # 呼叫 PUT /profiles/freelancer/skills
    skills_payload = {
        "skill_tag_ids": [react_id, node_id]
    }
    resp_skills = await client.put(
        "/profiles/freelancer/skills",
        json=skills_payload,
        headers=freelancer_auth_headers
    )
    assert resp_skills.status_code == 200
    
    # 驗證回傳的技能列表
    skills_data = resp_skills.json()
    assert len(skills_data) == 2
    returned_tag_names = {s["tag"]["name"] for s in skills_data}
    assert "React" in returned_tag_names
    assert "Node.js" in returned_tag_names

    # ==========================================
    # 3. 驗證 DB 關聯 (M2M Check)
    # ==========================================
    # 透過 API 查詢公開 Profile 來側面驗證 DB 讀取
    # 先獲取 user_id
    me_resp = await client.get("/profiles/me", headers=freelancer_auth_headers)
    user_id = me_resp.json()["user_id"]
    
    # 讀取公開 Profile
    public_resp = await client.get(f"/profiles/freelancer/{user_id}", headers=employer_auth_headers)
    assert public_resp.status_code == 200
    public_data = public_resp.json()
    assert len(public_data["skills"]) == 2

    # ==========================================
    # 4. 雇主搜尋人才 (Search Freelancers)
    # ==========================================
    # 測試情境 A: 搜尋 "React" (應該命中)
    # 注意：根據 router 實作，參數是 tag_id[]
    params_match = {"tag_id[]": [react_id]}
    
    resp_search_match = await client.get(
        "/profiles/freelancers/search", 
        params=params_match, 
        headers=employer_auth_headers
    )
    assert resp_search_match.status_code == 200
    results_match = resp_search_match.json()
    
    # 應該要找到至少一位 (剛剛那位)
    # (因為測試環境隔離，應該只有這一位符合)
    found_user_ids = [p["user_id"] for p in results_match]
    assert user_id in found_user_ids

    # 測試情境 B: 搜尋 "Go" (該工作者沒有 Go 技能，應該找不到)
    params_miss = {"tag_id[]": [go_id]}
    
    resp_search_miss = await client.get(
        "/profiles/freelancers/search", 
        params=params_miss, 
        headers=employer_auth_headers
    )
    assert resp_search_miss.status_code == 200
    results_miss = resp_search_miss.json()
    
    # 應該找不到該 user_id
    miss_user_ids = [p["user_id"] for p in results_miss]
    assert user_id not in miss_user_ids