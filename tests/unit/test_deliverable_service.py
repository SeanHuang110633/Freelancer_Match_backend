import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, UploadFile

from app.services.deliverable_service import DeliverableService
from app.models.contract import Contract
from app.models.deliverable import Deliverable
from app.models.user import User

# ==========================================
# Part 1: 上傳交付物 (Upload)
# ==========================================

@pytest.mark.asyncio
async def test_upload_deliverable_success(mock_db_session, mock_user_freelancer, mocker):
    """
    測試：工作者在進行中合約上傳交付物 (Happy Path)
    """
    # 1. Arrange
    # Mock Storage
    mock_storage = MagicMock()
    mock_storage.save_file = AsyncMock(return_value="http://storage/file.pdf")
    mocker.patch("app.services.deliverable_service.get_storage_provider", return_value=mock_storage)
    
    service = DeliverableService(mock_db_session)
    contract_id = "c1"
    
    # 模擬合約：進行中，且工作者是當前用戶
    mock_contract = Contract(
        contract_id=contract_id,
        status="進行中",
        freelancer_id=mock_user_freelancer.user_id
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    # Mock create
    mock_create = mocker.patch.object(service.repo, 'create_deliverable', return_value=Deliverable(deliverable_id="d1"))

    # 模擬上傳檔案
    mock_file = MagicMock(spec=UploadFile)

    # 2. Act
    result = await service.upload_deliverable(contract_id, mock_user_freelancer, mock_file, "說明")

    # 3. Assert
    assert result.deliverable_id == "d1"
    # 驗證 Storage 被呼叫
    mock_storage.save_file.assert_called_once_with(mock_file, directory="deliverables")
    # 驗證 DB 建立
    mock_create.assert_called_once()

@pytest.mark.asyncio
async def test_upload_deliverable_fail_wrong_status(mock_db_session, mock_user_freelancer, mocker):
    """測試：合約狀態鎖定 (非進行中不可上傳)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    # 模擬合約狀態為 "已完成"
    mock_contract = Contract(status="已完成", freelancer_id=mock_user_freelancer.user_id)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.upload_deliverable("c1", mock_user_freelancer, None, "desc")
    
    assert exc.value.status_code == 400
    assert "無法上傳" in exc.value.detail

@pytest.mark.asyncio
async def test_upload_deliverable_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：雇主不能上傳交付物"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    mock_contract = Contract(status="進行中", freelancer_id="worker_1") # 工作者是別人
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.upload_deliverable("c1", mock_user_employer, None, "desc")
    
    assert exc.value.status_code == 403

# ==========================================
# Part 2: 查詢與隱私 (Read & Privacy)
# ==========================================

@pytest.mark.asyncio
async def test_get_deliverables_employer_privacy(mock_db_session, mock_user_employer, mocker):
    """
    [關鍵測試] 測試：雇主在合約進行中時，應該看不到交付物列表 (回傳空 list)
    """
    service = DeliverableService(mock_db_session)
    
    mock_contract = Contract(
        contract_id="c1",
        status="進行中", # 還在進行中
        employer_id=mock_user_employer.user_id,
        freelancer_id="w1"
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    # 即使 Repo 有資料，Service 層也應該攔截
    mocker.patch.object(service.repo, 'list_deliverables_by_contract_id', return_value=[Deliverable()])

    result = await service.get_contract_deliverables("c1", mock_user_employer)
    
    assert result == [] # 應該被隱藏

@pytest.mark.asyncio
async def test_get_deliverables_freelancer_view(mock_db_session, mock_user_freelancer, mocker):
    """測試：工作者隨時可以看到自己的交付物"""
    service = DeliverableService(mock_db_session)
    mock_contract = Contract(status="進行中", freelancer_id=mock_user_freelancer.user_id, employer_id="boss")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    # (修正) 使用正確的欄位名稱 deliverable_id
    expected_list = [Deliverable(deliverable_id="d1")] 
    mocker.patch.object(service.repo, 'list_deliverables_by_contract_id', return_value=expected_list)

    result = await service.get_contract_deliverables("c1", mock_user_freelancer)
    assert result == expected_list

# ==========================================
# Part 3: 修改與刪除 (Update & Delete)
# ==========================================

@pytest.mark.asyncio
async def test_update_deliverable_success_replace_file(mock_db_session, mock_user_freelancer, mocker):
    """測試：修改交付物並替換檔案"""
    # Arrange
    mock_storage = MagicMock()
    mock_storage.save_file = AsyncMock(return_value="http://storage/new.pdf")
    mock_storage.delete_file = AsyncMock(return_value=True)
    mocker.patch("app.services.deliverable_service.get_storage_provider", return_value=mock_storage)
    
    service = DeliverableService(mock_db_session)
    
    # 交付物
    mock_deliverable = Deliverable(
        deliverable_id="d1", 
        contract_id="c1", 
        uploader_id=mock_user_freelancer.user_id,
        file_url="http://storage/old.pdf",
        acceptance_status="待驗收"
    )
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    
    # 合約 (必須是進行中)
    mock_contract = Contract(contract_id="c1", status="進行中")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    mock_update = mocker.patch.object(service.repo, 'update_deliverable', return_value=mock_deliverable)

    # Act
    new_file = MagicMock(spec=UploadFile)
    result = await service.update_deliverable("d1", mock_user_freelancer, new_file, "新說明")

    # Assert
    assert result.description == "新說明"
    assert result.file_url == "http://storage/new.pdf"
    
    mock_storage.delete_file.assert_called_once_with("http://storage/old.pdf")
    mock_storage.save_file.assert_called_once()
    mock_update.assert_called_once()

@pytest.mark.asyncio
async def test_delete_deliverable_fail_locked_status(mock_db_session, mock_user_freelancer, mocker):
    """測試：若已經進入驗收流程 (工作者要求驗收)，則鎖定刪除 (400)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    mock_deliverable = Deliverable(contract_id="c1", uploader_id=mock_user_freelancer.user_id)
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    
    # 合約狀態鎖定
    mock_contract = Contract(status="工作者要求驗收")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.delete_deliverable("d1", mock_user_freelancer)
    
    assert exc.value.status_code == 400
    assert "檔案目前已鎖定" in exc.value.detail

# ... (保留原本的 Part 1 ~ Part 3)

# ==========================================
# Part 4: 補強異常處理 (Error Handling) - 修復 404/403 分支
# ==========================================

@pytest.mark.asyncio
async def test_upload_deliverable_fail_contract_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：上傳時合約不存在 (404)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.upload_deliverable("c_404", mock_user_freelancer, None, "desc")
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_deliverables_fail_contract_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：查詢時合約不存在 (404)"""
    service = DeliverableService(mock_db_session)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.get_contract_deliverables("c_404", mock_user_freelancer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_deliverables_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非當事人查詢 (403)"""
    service = DeliverableService(mock_db_session)
    # 合約當事人跟這個 user 無關
    mock_contract = Contract(employer_id="other_boss", freelancer_id="other_worker")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.get_contract_deliverables("c1", mock_user_employer)
    assert exc.value.status_code == 403

# ==========================================
# Part 5: 補強更新邏輯 (Update Edge Cases)
# ==========================================

@pytest.mark.asyncio
async def test_update_deliverable_fail_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：更新不存在的交付物 (404)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.update_deliverable("d_404", mock_user_freelancer, None, "desc")
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_update_deliverable_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非上傳者嘗試修改 (403)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    mock_deliverable = Deliverable(uploader_id="other_guy", contract_id="c1")
    mock_contract = Contract(contract_id="c1", status="進行中")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.update_deliverable("d1", mock_user_employer, None, "desc")
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_update_deliverable_fail_contract_locked(mock_db_session, mock_user_freelancer, mocker):
    """測試：合約狀態非進行中 (鎖定) (400)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    mock_deliverable = Deliverable(uploader_id=mock_user_freelancer.user_id, contract_id="c1")
    # 合約已完成，不能改
    mock_contract = Contract(contract_id="c1", status="已完成")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.update_deliverable("d1", mock_user_freelancer, None, "desc")
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_update_deliverable_fail_acceptance_locked(mock_db_session, mock_user_freelancer, mocker):
    """測試：交付物狀態非待驗收 (鎖定) (400)"""
    mocker.patch("app.services.deliverable_service.get_storage_provider")
    service = DeliverableService(mock_db_session)
    
    # 交付物已通過，不能改
    mock_deliverable = Deliverable(
        uploader_id=mock_user_freelancer.user_id, 
        contract_id="c1", 
        acceptance_status="已通過"
    )
    mock_contract = Contract(contract_id="c1", status="進行中")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.update_deliverable("d1", mock_user_freelancer, None, "desc")
    assert exc.value.status_code == 400

# ==========================================
# Part 6: 補強刪除邏輯 (Delete Full Coverage)
# ==========================================

@pytest.mark.asyncio
async def test_delete_deliverable_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：成功刪除交付物 (含檔案刪除)"""
    # Arrange
    mock_storage = MagicMock()
    mock_storage.delete_file = AsyncMock(return_value=True)
    mocker.patch("app.services.deliverable_service.get_storage_provider", return_value=mock_storage)
    
    service = DeliverableService(mock_db_session)
    
    mock_deliverable = Deliverable(
        deliverable_id="d1",
        contract_id="c1",
        uploader_id=mock_user_freelancer.user_id,
        file_url="http://storage/file.pdf",
        acceptance_status="待驗收"
    )
    mock_contract = Contract(status="進行中")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mock_delete = mocker.patch.object(service.repo, 'delete_deliverable', new_callable=AsyncMock)

    # Act
    await service.delete_deliverable("d1", mock_user_freelancer)

    # Assert
    mock_storage.delete_file.assert_called_once_with("http://storage/file.pdf")
    mock_delete.assert_called_once()

@pytest.mark.asyncio
async def test_delete_deliverable_fail_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：刪除不存在的交付物 (404)"""
    service = DeliverableService(mock_db_session)
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=None)
    
    with pytest.raises(HTTPException) as exc:
        await service.delete_deliverable("d1", mock_user_freelancer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_delete_deliverable_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：刪除他人的交付物 (403)"""
    service = DeliverableService(mock_db_session)
    mock_deliverable = Deliverable(uploader_id="other", contract_id="c1")
    mock_contract = Contract(status="進行中")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.delete_deliverable("d1", mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_delete_deliverable_fail_acceptance_locked(mock_db_session, mock_user_freelancer, mocker):
    """測試：已驗收通過無法刪除 (400)"""
    service = DeliverableService(mock_db_session)
    mock_deliverable = Deliverable(
        uploader_id=mock_user_freelancer.user_id, 
        contract_id="c1",
        acceptance_status="已通過"
    )
    mock_contract = Contract(status="進行中")
    
    mocker.patch.object(service.repo, 'get_deliverable_by_id', return_value=mock_deliverable)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.delete_deliverable("d1", mock_user_freelancer)
    assert exc.value.status_code == 400