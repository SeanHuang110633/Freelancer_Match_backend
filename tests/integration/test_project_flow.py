import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.project import Project, ProjectSkillTag
from app.models.skill_tag import SkillTag

@pytest.mark.asyncio
async def test_employer_create_project_flow(
    client: AsyncClient,
    employer_auth_headers: dict, # 這是我們在 conftest.py 寫好的 Fixture
    db_session
):
    """
    【整合測試 P0】雇主刊登案件流程
    1. 準備技能標籤資料 (Arrange)
    2. 雇主發送刊登請求 (Act)
    3. 驗證 API 回應 (Assert)
    4. 驗證資料庫寫入狀態，特別是 M2M 關聯 (Assert)
    """
    # 1. Arrange: 先在 DB 塞幾個技能標籤供測試用
    # (注意：因為是 Transaction Rollback，這些標籤在測試後會自動消失)
    tag1 = SkillTag(name="Python", category="Backend")
    tag2 = SkillTag(name="FastAPI", category="Backend")
    db_session.add_all([tag1, tag2])
    await db_session.flush() # 取得 ID
    tag_ids = [tag1.tag_id, tag2.tag_id]

    payload = {
        "title": "Backend API Development",
        "description": "Need a FastAPI expert to build a scalable system.",
        "budget_min": 50000,
        "work_type": "遠端",
        "skill_tag_ids": tag_ids # 測試 M2M 寫入
    }

    # 2. Act: 刊登案件
    response = await client.post(
        "/projects/", 
        json=payload, 
        headers=employer_auth_headers
    )

    # 3. Assert API Response
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert "project_id" in data
    assert len(data["skills"]) == 2 # 確認回傳包含了技能
    
    # 驗證回傳的結構中有包含雇主資訊 (Eager Loading 檢查)
    assert data["employer"]["email"] == "integration_employer@example.com"

    # 4. Assert Database State
    project_id = data["project_id"]
    
    # 查詢 DB，並明確載入 skills
    stmt = select(Project).where(Project.project_id == project_id).options(
        selectinload(Project.skills)
    )
    result = await db_session.execute(stmt)
    db_project = result.scalars().first()

    assert db_project is not None
    assert db_project.title == "Backend API Development"
    assert db_project.status == "招募中"
    
    # 關鍵：驗證 ProjectSkillTag 關聯表是否有寫入
    # db_project.skills 是一個 list of ProjectSkillTag objects
    assert len(db_project.skills) == 2
    saved_tag_ids = {skill.tag_id for skill in db_project.skills}
    assert saved_tag_ids == set(tag_ids)

@pytest.mark.asyncio
async def test_search_projects(
    client: AsyncClient,
    employer_auth_headers: dict,
    freelancer_auth_headers: dict,
    db_session
):
    """
    【整合測試 P2】案件搜尋與 Eager Loading 驗證
    1. 建立兩筆案件，一筆有 Python 標籤，一筆沒有
    2. 使用工作者身分搜尋 "Python"
    3. 驗證篩選結果正確
    4. 驗證回傳資料結構包含必要的巢狀欄位 (前端顯示用)
    """
    # 1. Arrange: 準備資料
    # 建立標籤
    tag_python = SkillTag(name="Python-Search", category="Backend")
    tag_java = SkillTag(name="Java-Search", category="Backend")
    db_session.add_all([tag_python, tag_java])
    await db_session.flush()

    # 刊登案件 A (Python)
    await client.post("/projects/", headers=employer_auth_headers, json={
        "title": "Python Job",
        "description": "Python dev needed",
        "skill_tag_ids": [tag_python.tag_id]
    })
    
    # 刊登案件 B (Java)
    await client.post("/projects/", headers=employer_auth_headers, json={
        "title": "Java Job",
        "description": "Java dev needed",
        "skill_tag_ids": [tag_java.tag_id]
    })

    # 2. Act: 搜尋 "Python-Search" 的案件
    # 注意：API 參數傳遞方式 ?tag_id=...
    # httpx 的 params 支援 list: {"tag_id[]": [id1, id2]} 
    # (根據您的 API 實作，Query param 名稱可能是 tag_id 或 tag_id[])
    # 您的 router 寫法是: tag_ids_from_query = request.query_params.getlist("tag_id[]")
    
    params = {"tag_id[]": [tag_python.tag_id]}
    
    response = await client.get("/projects/", params=params, headers=freelancer_auth_headers)

    # 3. Assert
    assert response.status_code == 200
    results = response.json()
    
    # 應該只搜到 1 筆 (Python Job)
    assert len(results) == 1
    assert results[0]["title"] == "Python Job"
    
    # 4. 驗證巢狀結構 (確保前端能顯示公司名稱)
    # 您的 Schema 結構是: employer -> employer_profile -> company_name
    # 雖然測試帳號可能還沒建立 EmployerProfile，欄位可能是 null，但結構必須存在
    employer_info = results[0]["employer"]
    assert "employer_profile" in employer_info
    # 如果您在 conftest 的 employer_auth_headers 沒建立 profile，這裡會是 null
    # 但只要 key 存在就代表 Schema 正確