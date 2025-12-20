import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.project import Project, ProjectSkillTag
from app.models.skill_tag import SkillTag

@pytest.mark.asyncio
async def test_employer_create_project_flow(
    client: AsyncClient,
    employer_auth_headers: dict,
    db_session
):
    """
    【整合測試 P0】雇主刊登案件流程
    """
    # 1. Arrange
    tag1 = SkillTag(name="Python", category="Backend")
    tag2 = SkillTag(name="FastAPI", category="Backend")
    db_session.add_all([tag1, tag2])
    await db_session.flush()
    tag_ids = [tag1.tag_id, tag2.tag_id]

    payload = {
        "title": "Backend API Development",
        "description": "Need a FastAPI expert to build a scalable system.",
        "budget_min": 50000,
        "work_type": "遠端",
        "skill_tag_ids": tag_ids
    }

    # 2. Act
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
    assert len(data["skills"]) == 2
    
    assert data["employer"]["email"] == "integration_employer@example.com"

    # 4. Assert Database State
    project_id = data["project_id"]
    
    stmt = select(Project).where(Project.project_id == project_id).options(
        selectinload(Project.skills)
    )
    result = await db_session.execute(stmt)
    db_project = result.scalars().first()

    assert db_project is not None
    assert db_project.title == "Backend API Development"
    assert db_project.status == "招募中"
    
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
    """
    # 1. Arrange
    tag_python = SkillTag(name="Python-Search", category="Backend")
    tag_java = SkillTag(name="Java-Search", category="Backend")
    db_session.add_all([tag_python, tag_java])
    await db_session.flush()

    await client.post("/projects/", headers=employer_auth_headers, json={
        "title": "Python Job",
        "description": "Python dev needed",
        "skill_tag_ids": [tag_python.tag_id]
    })
    
    await client.post("/projects/", headers=employer_auth_headers, json={
        "title": "Java Job",
        "description": "Java dev needed",
        "skill_tag_ids": [tag_java.tag_id]
    })

    # 2. Act: 搜尋 "Python-Search" 的案件
    params = {"tag_id[]": [tag_python.tag_id]}
    
    response = await client.get("/projects/", params=params, headers=freelancer_auth_headers)

    # 3. Assert
    assert response.status_code == 200
    search_data = response.json()
    
    # 【修正】解析分頁結構
    # search_data 結構為 {"items": [...], "total": 1}
    results = search_data["items"]
    
    # 應該只搜到 1 筆 (Python Job)
    assert len(results) == 1
    assert results[0]["title"] == "Python Job"
    
    # 4. 驗證巢狀結構
    employer_info = results[0]["employer"]
    assert "employer_profile" in employer_info