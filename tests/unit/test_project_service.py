import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.project_service import ProjectService
from app.schemas.project_schema import ProjectCreate, ProjectUpdate, ProjectStatusUpdate
from app.models.project import Project
from app.models.proposal import Proposal
from app.models.user import User, UserRoleEnum

# ==========================================
# Part 1: 建立案件 (Create)
# ==========================================

@pytest.mark.asyncio
async def test_create_project_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主成功刊登案件 (含技能標籤驗證)"""
    # Arrange
    service = ProjectService(mock_db_session)
    project_data = ProjectCreate(
        title="新案件", 
        description="描述", 
        skill_tag_ids=["tag1", "tag2"]
    )
    
    # Mock Skill Repo: 驗證標籤全部存在 (回傳數量 = 輸入數量)
    mocker.patch.object(service.skill_tag_repo, 'count_tags_by_ids', return_value=2)
    
    # Mock Project Repo: 建立成功
    mock_new_project = Project(project_id="p_new", title="新案件")
    mocker.patch.object(service.project_repo, 'create_project', return_value=mock_new_project)

    # Act
    result = await service.create_project(project_data, mock_user_employer)

    # Assert
    assert result.project_id == "p_new"
    service.project_repo.create_project.assert_called_once()

@pytest.mark.asyncio
async def test_create_project_fail_invalid_skills(mock_db_session, mock_user_employer, mocker):
    """測試：包含無效的技能標籤 ID (400)"""
    service = ProjectService(mock_db_session)
    project_data = ProjectCreate(title="案子", description="...", skill_tag_ids=["tag1", "bad_tag"])
    
    # Mock Skill Repo: 只找到 1 個 (輸入 2 個，不匹配)
    mocker.patch.object(service.skill_tag_repo, 'count_tags_by_ids', return_value=1)

    with pytest.raises(HTTPException) as exc:
        await service.create_project(project_data, mock_user_employer)
    
    assert exc.value.status_code == 400
    assert "包含無效的技能標籤" in exc.value.detail

@pytest.mark.asyncio
async def test_create_project_fail_not_employer(mock_db_session, mock_user_freelancer, mocker):
    """測試：非雇主嘗試刊登 (403)"""
    service = ProjectService(mock_db_session)
    with pytest.raises(HTTPException) as exc:
        await service.create_project(ProjectCreate(title="t", description="d"), mock_user_freelancer)
    assert exc.value.status_code == 403

# ==========================================
# Part 2: 修改案件內容 (Update Content)
# ==========================================

@pytest.mark.asyncio
async def test_update_project_success_and_notify(mock_db_session, mock_user_employer, mocker):
    """測試：修改案件內容成功，並通知已提案者"""
    # Arrange
    service = ProjectService(mock_db_session)
    project_id = "p1"
    
    # 模擬現有案件
    mock_project = Project(
        project_id=project_id, 
        employer_id=mock_user_employer.user_id, 
        status="招募中",
        title="舊標題"
    )
    
    # 模擬提案 (用於測試通知)
    mock_proposal = Proposal(
        freelancer_id="worker_1", 
        status="已提交"
    )
    # 讓 get_project_by_id 回傳 mock_project
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    
    # 讓 get_project_by_id_with_proposals 回傳帶有提案的物件
    mock_project_with_proposals = Project(project_id=project_id, proposals=[mock_proposal])
    mocker.patch.object(service.project_repo, 'get_project_by_id_with_proposals', return_value=mock_project_with_proposals)
    
    # Mock update Repo
    mocker.patch.object(service.project_repo, 'update_project', return_value=mock_project)
    
    # Mock Notification
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    update_data = ProjectUpdate(title="新標題")

    # Act
    await service.update_project(project_id, update_data, mock_user_employer)

    # Assert
    assert mock_project.title == "新標題"
    service.project_repo.update_project.assert_called_once()
    # 驗證通知發送
    mock_notify.assert_called_once()
    assert mock_notify.call_args[1]['user_id'] == "worker_1"
    assert "案件更新通知" in mock_notify.call_args[1]['title']

@pytest.mark.asyncio
async def test_update_project_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非案主嘗試修改 (403)"""
    service = ProjectService(mock_db_session)
    mock_project = Project(project_id="p1", employer_id="other_boss", status="招募中")
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    with pytest.raises(HTTPException) as exc:
        await service.update_project("p1", ProjectUpdate(title="new"), mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_update_project_fail_wrong_status(mock_db_session, mock_user_employer, mocker):
    """測試：案件非 '招募中' 不可修改 (400)"""
    service = ProjectService(mock_db_session)
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id, status="已關閉")
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    with pytest.raises(HTTPException) as exc:
        await service.update_project("p1", ProjectUpdate(title="new"), mock_user_employer)
    assert exc.value.status_code == 400

# ==========================================
# Part 3: 更新狀態/關閉案件 (Cascading Status Update)
# ==========================================

@pytest.mark.asyncio
async def test_close_project_cascading_updates(mock_db_session, mock_user_employer, mocker):
    """
    [關鍵測試] 測試：關閉案件時，是否連鎖更新提案狀態並發送通知
    """
    # Arrange
    service = ProjectService(mock_db_session)
    project_id = "p1"
    
    mock_project = Project(
        project_id=project_id, 
        employer_id=mock_user_employer.user_id, 
        status="招募中",
        title="測試專案"
    )
    
    # 模擬兩個提案：一個 '已提交' (應被撤銷)，一個 '已拒絕' (不應受影響)
    prop_active = Proposal(proposal_id="prop_1", freelancer_id="w1", status="已提交")
    prop_rejected = Proposal(proposal_id="prop_2", freelancer_id="w2", status="已拒絕")
    
    mock_project_with_props = Project(
        project_id=project_id, 
        proposals=[prop_active, prop_rejected]
    )

    # Mocks
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    mocker.patch.object(service.project_repo, 'get_project_by_id_with_proposals', return_value=mock_project_with_props)
    
    # Mock Repo Actions
    mock_update_proj = mocker.patch.object(service.project_repo, 'update_project', return_value=mock_project)
    mock_update_prop = mocker.patch.object(service.proposal_repo, 'update_proposal', new_callable=AsyncMock)
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    status_data = ProjectStatusUpdate(status="已關閉")

    # Act
    await service.update_project_status(project_id, status_data, mock_user_employer)

    # Assert
    # 1. 案件狀態變更
    assert mock_project.status == "已關閉"
    mock_update_proj.assert_called_once()

    # 2. 提案狀態變更 (只應更新 prop_active)
    assert prop_active.status == "雇主已撤銷案件"
    mock_update_prop.assert_called_once_with(prop_active) 
    # 確保 prop_rejected 沒被更新
    assert prop_rejected.status == "已拒絕"

    # 3. 通知發送 (只發給 prop_active 的 w1)
    mock_notify.assert_called_once()
    assert mock_notify.call_args[1]['user_id'] == "w1"
    assert "案件關閉通知" in mock_notify.call_args[1]['title']

@pytest.mark.asyncio
async def test_update_status_fail_invalid_transition(mock_db_session, mock_user_employer, mocker):
    """測試：嘗試更新為非 '已關閉' 的狀態 (API 限制)"""
    service = ProjectService(mock_db_session)
    # 根據 service 邏輯，目前只支援轉為 "已關閉"
    with pytest.raises(HTTPException) as exc:
        await service.update_project_status("p1", ProjectStatusUpdate(status="已成案"), mock_user_employer)
    assert exc.value.status_code == 400

# ==========================================
# Part 4: 其他查詢 (Read)
# ==========================================

@pytest.mark.asyncio
async def test_get_my_projects_role_check(mock_db_session, mock_user_freelancer, mocker):
    """測試：工作者不能呼叫 get_my_projects"""
    service = ProjectService(mock_db_session)
    with pytest.raises(HTTPException) as exc:
        await service.get_my_projects(mock_user_freelancer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_get_project_details_not_found(mock_db_session, mocker):
    """測試：案件不存在"""
    service = ProjectService(mock_db_session)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=None)
    with pytest.raises(HTTPException) as exc:
        await service.get_project_details("p_404")
    assert exc.value.status_code == 404