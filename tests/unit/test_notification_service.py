import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.notification_service import NotificationService
from app.models.notification import Notification
from app.models.user import User

# ==========================================
# Part 1: 建立與查詢 (Create & Read)
# ==========================================

@pytest.mark.asyncio
async def test_create_notification_success(mock_db_session, mocker):
    """測試：內部建立通知功能"""
    # Arrange
    service = NotificationService(mock_db_session)
    mock_note = Notification(notification_id="n1", title="Title")
    mocker.patch.object(service.repo, 'create_notification', return_value=mock_note)

    # Act
    result = await service.create_notification(
        user_id="u1", 
        title="Title", 
        link_url="http://link", 
        message="msg"
    )

    # Assert
    assert result.notification_id == "n1"
    # 驗證參數是否正確傳遞給 Repo
    service.repo.create_notification.assert_called_once()
    call_arg = service.repo.create_notification.call_args[0][0]
    assert call_arg.user_id == "u1"
    assert call_arg.title == "Title"
    assert call_arg.link_url == "http://link"
    assert call_arg.is_read is False

@pytest.mark.asyncio
async def test_get_my_notifications(mock_db_session, mock_user_freelancer, mocker):
    """測試：獲取我的通知列表"""
    service = NotificationService(mock_db_session)
    mock_list = [Notification(notification_id="n1"), Notification(notification_id="n2")]
    mocker.patch.object(service.repo, 'list_notifications_by_user', return_value=mock_list)

    result = await service.get_my_notifications(mock_user_freelancer)

    assert len(result) == 2
    service.repo.list_notifications_by_user.assert_called_once_with(mock_user_freelancer.user_id)

# ==========================================
# Part 2: 標記已讀 (Mark as Read) - 重點邏輯
# ==========================================

@pytest.mark.asyncio
async def test_mark_as_read_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：成功將未讀通知標記為已讀"""
    service = NotificationService(mock_db_session)
    
    # 模擬一個 "未讀" 且 "屬於我" 的通知
    mock_note = Notification(
        notification_id="n1", 
        user_id=mock_user_freelancer.user_id, 
        is_read=False
    )
    mocker.patch.object(service.repo, 'get_notification_by_id', return_value=mock_note)
    mocker.patch.object(service.repo, 'mark_as_read', return_value=mock_note)

    # Act
    await service.mark_notification_as_read("n1", mock_user_freelancer)

    # Assert
    service.repo.mark_as_read.assert_called_once_with(mock_note)

@pytest.mark.asyncio
async def test_mark_as_read_idempotency(mock_db_session, mock_user_freelancer, mocker):
    """測試：若已經已讀，不應再次呼叫 DB 更新 (冪等性)"""
    service = NotificationService(mock_db_session)
    
    # 模擬一個 "已讀" 的通知
    mock_note = Notification(
        notification_id="n1", 
        user_id=mock_user_freelancer.user_id, 
        is_read=True 
    )
    mocker.patch.object(service.repo, 'get_notification_by_id', return_value=mock_note)
    mock_update = mocker.patch.object(service.repo, 'mark_as_read')

    # Act
    result = await service.mark_notification_as_read("n1", mock_user_freelancer)

    # Assert
    assert result.is_read is True
    # 關鍵：不應該呼叫 repo.mark_as_read
    mock_update.assert_not_called()

@pytest.mark.asyncio
async def test_mark_as_read_fail_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：通知不存在 (404)"""
    service = NotificationService(mock_db_session)
    mocker.patch.object(service.repo, 'get_notification_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.mark_notification_as_read("n_404", mock_user_freelancer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_mark_as_read_fail_permission(mock_db_session, mock_user_freelancer, mocker):
    """測試：嘗試標記別人的通知 (403)"""
    service = NotificationService(mock_db_session)
    
    # 通知屬於別人
    mock_note = Notification(
        notification_id="n1", 
        user_id="other_user", 
        is_read=False
    )
    mocker.patch.object(service.repo, 'get_notification_by_id', return_value=mock_note)

    with pytest.raises(HTTPException) as exc:
        await service.mark_notification_as_read("n1", mock_user_freelancer)
    
    assert exc.value.status_code == 403
    assert "無權操作" in exc.value.detail