import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, UploadFile

from app.services.proposal_service import ProposalService
from app.schemas.proposal_schema import ProposalCreate
from app.models.project import Project
from app.models.proposal import Proposal

# ==========================================
# Part 1: 建立提案 (Create) - 原有測試
# ==========================================

@pytest.mark.asyncio
async def test_create_proposal_success_and_notify(mock_db_session, mock_user_freelancer, mocker):
    """
    測試重點：成功提案流程 (Storage + Notification)
    """
    # 1. Arrange
    project_id = "proj_001"
    
    # Mock Storage
    mock_storage_instance = MagicMock()
    mock_storage_instance.save_file = AsyncMock(return_value="http://mock-storage/resume.pdf")
    mocker.patch("app.services.proposal_service.get_storage_provider", return_value=mock_storage_instance)

    service = ProposalService(mock_db_session)

    # Mock Repos
    mock_project = Project(
        project_id=project_id, 
        employer_id="emp_123", 
        title="測試案件", 
        status="招募中"
    )
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    mocker.patch.object(service.proposal_repo, 'check_existing_proposal', return_value=None)
    
    expected_proposal = Proposal(proposal_id="prop_new", status="已提交", attachment_url="http://mock-storage/resume.pdf")
    mocker.patch.object(service.proposal_repo, 'create_proposal', return_value=expected_proposal)

    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    proposal_data = ProposalCreate(brief_description="我能做")
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.pdf"

    # 2. Act
    result = await service.create_proposal(project_id, mock_user_freelancer, proposal_data, mock_file)

    # 3. Assert
    assert result.status == "已提交"
    mock_storage_instance.save_file.assert_called_once()
    mock_notify.assert_called_once()

@pytest.mark.asyncio
async def test_create_proposal_permission_denied(mock_db_session, mock_user_employer, mocker):
    """測試：雇主不能提案"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    proposal_data = ProposalCreate(brief_description="...")
    
    with pytest.raises(HTTPException) as exc:
        await service.create_proposal("p1", mock_user_employer, proposal_data, None)
    
    assert exc.value.status_code == 403

# ==========================================
# Part 2: 撤回提案 (Delete) - 補完邏輯
# ==========================================

@pytest.mark.asyncio
async def test_delete_proposal_success_removes_file(mock_db_session, mock_user_freelancer, mocker):
    """測試：成功撤回提案並刪除檔案"""
    # Arrange
    mock_storage = MagicMock()
    mock_storage.delete_file = AsyncMock(return_value=True)
    mocker.patch("app.services.proposal_service.get_storage_provider", return_value=mock_storage)
    
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id=mock_user_freelancer.user_id,
        status="已提交",
        attachment_url="http://mock/old.pdf"
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)
    mock_delete_repo = mocker.patch.object(service.proposal_repo, 'delete_proposal', new_callable=AsyncMock)

    # Act
    await service.delete_proposal("p1", mock_user_freelancer)

    # Assert
    mock_storage.delete_file.assert_called_once_with("http://mock/old.pdf")
    mock_delete_repo.assert_called_once_with(mock_proposal)

@pytest.mark.asyncio
async def test_delete_proposal_fail_status(mock_db_session, mock_user_freelancer, mocker):
    """測試：若提案已被接受，無法撤回 (400)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id=mock_user_freelancer.user_id,
        status="已接受" # 狀態不對
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.delete_proposal("p1", mock_user_freelancer)
    
    assert exc.value.status_code == 400
    assert "已被處理" in exc.value.detail

@pytest.mark.asyncio
async def test_delete_proposal_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非提案本人無法撤回 (403)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id="other_worker", # 擁有者不是當前用戶
        status="已提交"
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.delete_proposal("p1", mock_user_employer)
    
    assert exc.value.status_code == 403

# ==========================================
# Part 3: 修改提案 (Update) - 新增 P1
# ==========================================

@pytest.mark.asyncio
async def test_update_proposal_success_replace_file(mock_db_session, mock_user_freelancer, mocker):
    """測試：修改提案並替換檔案 (上傳新檔 + 刪除舊檔)"""
    # Arrange
    mock_storage = MagicMock()
    mock_storage.save_file = AsyncMock(return_value="http://mock/new.pdf")
    mock_storage.delete_file = AsyncMock(return_value=True)
    mocker.patch("app.services.proposal_service.get_storage_provider", return_value=mock_storage)
    
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id=mock_user_freelancer.user_id,
        status="已提交",
        attachment_url="http://mock/old.pdf"
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)
    mock_update_repo = mocker.patch.object(service.proposal_repo, 'update_proposal', return_value=mock_proposal)

    new_file = MagicMock(spec=UploadFile)

    # Act
    result = await service.update_proposal(
        "p1", 
        mock_user_freelancer, 
        brief_description="新描述", 
        attachment=new_file
    )

    # Assert
    assert result.brief_description == "新描述"
    assert result.attachment_url == "http://mock/new.pdf"
    
    # 驗證舊檔案被刪除，新檔案被儲存
    mock_storage.delete_file.assert_called_once_with("http://mock/old.pdf")
    mock_storage.save_file.assert_called_once()
    mock_update_repo.assert_called_once()

@pytest.mark.asyncio
async def test_update_proposal_fail_status(mock_db_session, mock_user_freelancer, mocker):
    """測試：提案若已被處理，無法修改 (400)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        status="已拒絕", # 狀態鎖定
        freelancer_id=mock_user_freelancer.user_id
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal("p1", mock_user_freelancer, "desc", None)
    
    assert exc.value.status_code == 400

# ==========================================
# Part 4: 查詢詳情 (Get Details) - 新增 P1
# ==========================================

@pytest.mark.asyncio
async def test_get_proposal_details_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：查看他人提案詳情 (403)"""
    # 這裡是指工作者看自己的提案詳情，如果傳入的 user id 不對應則拒絕
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id="other_worker"
    )
    # 注意：這裡 Mock 的是 get_proposal_by_id_with_details
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_details', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.get_proposal_details("p1", mock_user_employer)
    
    assert exc.value.status_code == 403

# ... (保留原本的 Part 1 ~ Part 4)

# ==========================================
# Part 5: 補強異常處理 (Error Handling) - 針對 Line 48, 51, 55
# ==========================================

@pytest.mark.asyncio
async def test_create_proposal_fail_project_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：案件不存在 (404)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.create_proposal("p1", mock_user_freelancer, ProposalCreate(brief_description="desc"), None)
    
    assert exc.value.status_code == 404
    assert "案件不存在" in exc.value.detail

@pytest.mark.asyncio
async def test_create_proposal_fail_project_status_invalid(mock_db_session, mock_user_freelancer, mocker):
    """測試：案件非招募中 (400)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_project = Project(project_id="p1", status="已關閉")
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    with pytest.raises(HTTPException) as exc:
        await service.create_proposal("p1", mock_user_freelancer, ProposalCreate(brief_description="desc"), None)
    
    assert exc.value.status_code == 400
    assert "未在招募中" in exc.value.detail

@pytest.mark.asyncio
async def test_create_proposal_fail_duplicate(mock_db_session, mock_user_freelancer, mocker):
    """測試：重複提案 (400)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_project = Project(project_id="p1", status="招募中")
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    
    # 模擬已存在提案
    mocker.patch.object(service.proposal_repo, 'check_existing_proposal', return_value=True)

    with pytest.raises(HTTPException) as exc:
        await service.create_proposal("p1", mock_user_freelancer, ProposalCreate(brief_description="desc"), None)
    
    assert exc.value.status_code == 400
    assert "已經對此案件提案" in exc.value.detail

# ==========================================
# Part 6: 補強修改提案 (Update) - 針對 Line 109, 112, 141
# ==========================================

@pytest.mark.asyncio
async def test_update_proposal_fail_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：修改不存在的提案 (404)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal("p1", mock_user_freelancer, "desc", None)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_update_proposal_fail_permission(mock_db_session, mock_user_freelancer, mocker):
    """測試：修改他人提案 (403)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(proposal_id="p1", freelancer_id="other_guy")
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal("p1", mock_user_freelancer, "desc", None)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_update_proposal_success_no_file(mock_db_session, mock_user_freelancer, mocker):
    """測試：僅修改描述，不換檔案"""
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id=mock_user_freelancer.user_id,
        status="已提交",
        attachment_url="http://old.url"
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id', return_value=mock_proposal)
    mock_update = mocker.patch.object(service.proposal_repo, 'update_proposal', return_value=mock_proposal)

    # Act: attachment=None
    result = await service.update_proposal("p1", mock_user_freelancer, "新描述", None)

    # Assert
    assert result.brief_description == "新描述"
    assert result.attachment_url == "http://old.url" # 網址沒變
    mock_update.assert_called_once()

# ==========================================
# Part 7: 補強讀取與狀態變更 (Read & Status) - 針對 Line 157-183
# ==========================================

@pytest.mark.asyncio
async def test_get_proposal_details_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：詳情不存在 (404)"""
    service = ProposalService(mock_db_session)
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_details', return_value=None)
    
    with pytest.raises(HTTPException) as exc:
        await service.get_proposal_details("p1", mock_user_freelancer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_project_with_proposals_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主獲取案件提案列表 (Happy Path)"""
    service = ProposalService(mock_db_session)
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id_with_proposals', return_value=mock_project)

    result = await service.get_project_with_proposals("p1", mock_user_employer)
    assert result.project_id == "p1"

@pytest.mark.asyncio
async def test_get_project_with_proposals_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非雇主獲取提案列表 (403)"""
    service = ProposalService(mock_db_session)
    mock_project = Project(project_id="p1", employer_id="other_boss")
    mocker.patch.object(service.project_repo, 'get_project_by_id_with_proposals', return_value=mock_project)

    with pytest.raises(HTTPException) as exc:
        await service.get_project_with_proposals("p1", mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_update_proposal_status_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主接受提案 (Happy Path)"""
    service = ProposalService(mock_db_session)
    
    mock_proposal = Proposal(
        proposal_id="p1",
        status="已提交",
        freelancer_id="w1",
        project=Project(employer_id=mock_user_employer.user_id, title="案子")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project', return_value=mock_proposal)
    mock_update = mocker.patch.object(service.proposal_repo, 'update_proposal', return_value=mock_proposal)
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    # Act: 接受
    await service.update_proposal_status("p1", "已接受", mock_user_employer)

    # Assert
    assert mock_proposal.status == "已接受"
    mock_notify.assert_called_once()
    mock_update.assert_called_once()

@pytest.mark.asyncio
async def test_update_proposal_status_fail_invalid_status(mock_db_session, mock_user_employer, mocker):
    """測試：傳入無效狀態 (400)"""
    service = ProposalService(mock_db_session)
    with pytest.raises(HTTPException) as exc:
        await service.update_proposal_status("p1", "亂寫的狀態", mock_user_employer)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_proposal_status_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：提案不存在 (404) for update_proposal_status"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal_status("p1", "已接受", mock_user_employer)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_proposal_status_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非雇主修改提案狀態 (403)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)

    mock_proposal = Proposal(
        proposal_id="p1",
        status="已提交",
        freelancer_id="w1",
        project=Project(employer_id="someone_else", title="案子")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal_status("p1", "已接受", mock_user_employer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_proposal_status_fail_already_processed(mock_db_session, mock_user_employer, mocker):
    """測試：提案已被處理，無法再變更狀態 (400)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)

    mock_proposal = Proposal(
        proposal_id="p1",
        status="已拒絕",
        freelancer_id="w1",
        project=Project(employer_id=mock_user_employer.user_id, title="案子")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.update_proposal_status("p1", "已接受", mock_user_employer)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_proposal_status_reject_triggers_notification(mock_db_session, mock_user_employer, mocker):
    """測試：雇主拒絕提案會通知工作者 (已拒絕)"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)

    mock_proposal = Proposal(
        proposal_id="p1",
        status="已提交",
        freelancer_id="w1",
        project=Project(employer_id=mock_user_employer.user_id, title="案子")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project', return_value=mock_proposal)
    mock_update = mocker.patch.object(service.proposal_repo, 'update_proposal', return_value=mock_proposal)
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    await service.update_proposal_status("p1", "已拒絕", mock_user_employer)

    assert mock_proposal.status == "已拒絕"
    mock_notify.assert_called_once()
    mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_get_proposal_details_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：工作者成功取得自己的提案詳情"""
    mocker.patch("app.services.proposal_service.get_storage_provider")
    service = ProposalService(mock_db_session)

    mock_proposal = Proposal(
        proposal_id="p1",
        freelancer_id=mock_user_freelancer.user_id
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_details', return_value=mock_proposal)

    result = await service.get_proposal_details("p1", mock_user_freelancer)
    assert result.proposal_id == "p1"