import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
import json
from datetime import datetime
import asyncio

from app.services.message_service import MessageService
from app.schemas.message_schema import RoomCreate, MessageIn
from app.models.message import ChatRoom, Message, ChatRoomParticipant
from app.models.project import Project
from app.models.user import User

# ==========================================
# Part 1: 建立聊天室 (Create Room)
# ==========================================

@pytest.mark.asyncio
async def test_create_chat_room_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主邀請工作者建立聊天室 (Happy Path)"""
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    mocker.patch.object(service.message_repo, 'find_room_by_participants', return_value=None)
    
    # (修正) 補上 created_at
    mock_new_room = ChatRoom(
        room_id="room_1", 
        context_project_id="p1",
        created_at=datetime.now(), 
        participants=[]
    )
    mocker.patch.object(service.message_repo, 'create_room_and_participants', return_value=mock_new_room)

    room_data = RoomCreate(project_id="p1", invited_user_id="worker_1")

    result = await service.create_chat_room(room_data, mock_user_employer)

    assert result.room_id == "room_1"
    service.message_repo.create_room_and_participants.assert_called_once()

@pytest.mark.asyncio
async def test_create_chat_room_fail_permission(mock_db_session, mock_user_freelancer, mocker):
    """測試：非專案相關人員嘗試建立聊天室 (403)"""
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    
    mock_project = Project(project_id="p1", employer_id="other_boss")
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    room_data = RoomCreate(project_id="p1", invited_user_id="worker_2")

    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(room_data, mock_user_freelancer)
    
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_create_chat_room_return_existing(mock_db_session, mock_user_employer, mocker):
    """測試：若聊天室已存在，直接回傳舊的"""
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    
    existing_room = ChatRoom(
        room_id="old_room", 
        created_at=datetime.now(),
        participants=[]
    )
    mocker.patch.object(service.message_repo, 'find_room_by_participants', return_value=existing_room)

    # (修正) 必須 Mock 這個方法，才能在最後 assert_not_called
    mock_create = mocker.patch.object(service.message_repo, 'create_room_and_participants')

    result = await service.create_chat_room(
        RoomCreate(project_id="p1", invited_user_id="w1"), 
        mock_user_employer
    )
    
    assert result.room_id == "old_room"
    
    # 使用我們剛剛建立的 mock 物件來驗證
    mock_create.assert_not_called()

# ==========================================
# Part 2: 查詢與權限 (Read & Permission)
# ==========================================

@pytest.mark.asyncio
async def test_get_room_messages_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：成員獲取歷史訊息，並觸發標記已讀"""
    service = MessageService(mock_db_session, AsyncMock())
    
    mock_room = ChatRoom(participants=[ChatRoomParticipant(user_id=mock_user_freelancer.user_id)])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    
    # (修正) 補上所有 Pydantic 必填欄位
    mock_sender = User(
        user_id="sender_1", 
        email="a@b.com", 
        role="自由工作者", 
        is_active=True
    )
    mock_msgs = [
        Message(
            message_id="m1", 
            room_id="room_1", 
            sender_id="sender_1",
            content="hi", 
            content_type="text",
            is_read=False,
            created_at=datetime.now(),
            sender=mock_sender
        )
    ]
    mocker.patch.object(service.message_repo, 'get_messages_by_room_id', return_value=mock_msgs)
    
    mock_mark_read = mocker.patch.object(service.message_repo, 'mark_messages_as_read', new_callable=AsyncMock)

    result = await service.get_room_messages("room_1", mock_user_freelancer)

    assert len(result) == 1
    assert result[0].content == "hi"
    mock_mark_read.assert_called_once_with("room_1", mock_user_freelancer.user_id)

@pytest.mark.asyncio
async def test_check_permission_fail(mock_db_session, mock_user_freelancer, mocker):
    """測試：非成員檢查權限失敗"""
    service = MessageService(mock_db_session, AsyncMock())
    mock_room = ChatRoom(participants=[ChatRoomParticipant(user_id="other_guy")])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)

    has_perm = await service.check_user_room_permission("room_1", mock_user_freelancer)
    assert has_perm is False

# ==========================================
# Part 3: 處理 WebSocket 訊息 (Handle Message)
# ==========================================

@pytest.mark.asyncio
async def test_handle_websocket_message_success(mock_db_session, mocker):
    """
    [關鍵測試] 測試：處理 WS 訊息流程 (DB -> Notify -> Publish)
    """
    # Arrange
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    
    room_id = "room_1"
    sender_id = "sender_1"
    raw_data = json.dumps({"content": "Hello World", "content_type": "text"})
    
    mock_room = ChatRoom(
        room_id=room_id, 
        project=Project(title="Proj"),
        participants=[
            ChatRoomParticipant(user_id=sender_id),
            ChatRoomParticipant(user_id="receiver_1")
        ]
    )
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    
    # (修正) 補上所有 Pydantic 必填欄位
    mock_sender = User(
        user_id=sender_id, 
        email="s@test.com", 
        role="自由工作者", 
        is_active=True
    )
    mock_saved_msg = Message(
        message_id="msg_new",
        room_id=room_id,
        sender_id=sender_id,
        content="Hello World", 
        content_type="text",
        is_read=False,
        created_at=datetime.now(),
        sender=mock_sender
    )
    mocker.patch.object(service.message_repo, 'save_message', return_value=mock_saved_msg)
    
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    # Act
    await service.handle_websocket_message(room_id, sender_id, raw_data)

    # Assert
    service.message_repo.save_message.assert_called_once()
    mock_notify.assert_called_once()
    mock_redis.publish.assert_called_once()
    
    channel = mock_redis.publish.call_args[0][0]
    payload = mock_redis.publish.call_args[0][1]
    
    assert channel == f"chat:{room_id}"
    assert b"Hello World" in payload

# ==========================================
# Part 4: 補強 create_chat_room 異常處理
# ==========================================

@pytest.mark.asyncio
async def test_create_chat_room_fail_project_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：案件不存在 (404)"""
    service = MessageService(mock_db_session, AsyncMock())
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(RoomCreate(project_id="p_404"), mock_user_employer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_create_chat_room_fail_employer_missing_invited(mock_db_session, mock_user_employer, mocker):
    """測試：雇主建立時未指定邀請對象 (400)"""
    service = MessageService(mock_db_session, AsyncMock())
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    # invited_user_id 為 None
    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(RoomCreate(project_id="p1", invited_user_id=None), mock_user_employer)
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_create_chat_room_fail_self_chat(mock_db_session, mock_user_employer, mocker):
    """測試：嘗試跟自己建立聊天室 (400)"""
    service = MessageService(mock_db_session, AsyncMock())
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)

    # 邀請對象就是雇主自己
    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(
            RoomCreate(project_id="p1", invited_user_id=mock_user_employer.user_id), 
            mock_user_employer
        )
    assert exc.value.status_code == 400
    assert "重複" in exc.value.detail

@pytest.mark.asyncio
async def test_create_chat_room_db_error(mock_db_session, mock_user_employer, mocker):
    """測試：資料庫建立失敗 (500)"""
    service = MessageService(mock_db_session, AsyncMock())
    mock_project = Project(project_id="p1", employer_id=mock_user_employer.user_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    mocker.patch.object(service.message_repo, 'find_room_by_participants', return_value=None)
    
    # 模擬 create 拋出例外
    mocker.patch.object(service.message_repo, 'create_room_and_participants', side_effect=Exception("DB Error"))

    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(RoomCreate(project_id="p1", invited_user_id="w1"), mock_user_employer)
    
    assert exc.value.status_code == 500
    mock_db_session.rollback.assert_called_once()

# ==========================================
# Part 5: 補強查詢 (Get User Rooms)
# ==========================================

@pytest.mark.asyncio
async def test_get_user_rooms_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：成功獲取聊天室列表"""
    service = MessageService(mock_db_session, AsyncMock())
    
    # 模擬 Repo 回傳 (需包含 created_at 以通過 Pydantic 驗證)
    mock_rooms = [
        ChatRoom(room_id="r1", context_project_id="p1", created_at=datetime.now(), participants=[]),
        ChatRoom(room_id="r2", context_project_id="p2", created_at=datetime.now(), participants=[])
    ]
    mocker.patch.object(service.message_repo, 'get_rooms_by_user_id', return_value=mock_rooms)

    result = await service.get_user_rooms(mock_user_freelancer)
    assert len(result) == 2
    assert result[0].room_id == "r1"

# ==========================================
# Part 6: 補強訊息讀取與權限 (Get Messages)
# ==========================================

@pytest.mark.asyncio
async def test_get_room_messages_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非成員讀取訊息 (403)"""
    service = MessageService(mock_db_session, AsyncMock())
    
    # 房間成員不含當前用戶
    mock_room = ChatRoom(participants=[ChatRoomParticipant(user_id="other")])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)

    with pytest.raises(HTTPException) as exc:
        await service.get_room_messages("r1", mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_get_room_messages_mark_read_error_logged(mock_db_session, mock_user_freelancer, mocker):
    """測試：標記已讀失敗時不應中斷流程，僅記錄 Log"""
    service = MessageService(mock_db_session, AsyncMock())
    
    # 正常成員
    mock_room = ChatRoom(participants=[ChatRoomParticipant(user_id=mock_user_freelancer.user_id)])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    mocker.patch.object(service.message_repo, 'get_messages_by_room_id', return_value=[])
    
    # 模擬 mark_read 拋出例外
    mocker.patch.object(service.message_repo, 'mark_messages_as_read', side_effect=Exception("Update Fail"))
    
    # 應該正常回傳空列表，不會拋出例外
    result = await service.get_room_messages("r1", mock_user_freelancer)
    assert result == []
    mock_db_session.rollback.assert_called_once()

# ==========================================
# Part 7: 補強 WebSocket 處理 (Handle Message Error)
# ==========================================

@pytest.mark.asyncio
async def test_handle_websocket_message_fail_room_not_found(mock_db_session, mocker):
    """測試：WebSocket 收到不存在的房間 ID"""
    service = MessageService(mock_db_session, AsyncMock())
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=None)
    
    raw_data = json.dumps({"content": "hi", "content_type": "text"})
    
    with pytest.raises(ValueError) as exc:
        await service.handle_websocket_message("r_404", "u1", raw_data)
    assert "not found" in str(exc.value)

@pytest.mark.asyncio
async def test_handle_websocket_message_db_error(mock_db_session, mocker):
    """測試：WebSocket 處理過程 DB 錯誤 (Rollback)"""
    service = MessageService(mock_db_session, AsyncMock())
    
    mock_room = ChatRoom(participants=[])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    
    # 模擬存訊息失敗
    mocker.patch.object(service.message_repo, 'save_message', side_effect=Exception("Save Fail"))

    raw_data = json.dumps({"content": "hi", "content_type": "text"})

    with pytest.raises(ValueError) as exc:
        await service.handle_websocket_message("r1", "u1", raw_data)
    
    assert "Message processing error" in str(exc.value)
    mock_db_session.rollback.assert_called_once()

# ==========================================
# Part 8: ConnectionManager 測試 (補強覆蓋率)
# 涵蓋範圍: connect, disconnect, broadcast_to_local_clients
# ==========================================

from app.services.message_service import manager, ConnectionManager

@pytest.mark.asyncio
async def test_manager_connect_and_disconnect_flow(mocker):
    """
    測試：ConnectionManager 的連線與斷線流程
    驗證：
    1. WebSocket accept 被呼叫
    2. local_connections 正確新增
    3. 背景任務 (Redis Listener) 被啟動
    4. 斷線後資源被清理
    """
    # Arrange
    room_id = "room_test"
    user_id = "u1"
    mock_ws = AsyncMock()
    
    # Mock asyncio.create_task 避免真的跑無窮迴圈
    mock_create_task = mocker.patch("asyncio.create_task")
    
    # 確保測試開始前是乾淨的
    if room_id in manager.local_connections:
        del manager.local_connections[room_id]
    if room_id in manager.listener_tasks:
        del manager.listener_tasks[room_id]

    # --- Act 1: Connect ---
    await manager.connect(room_id, user_id, mock_ws)

    # Assert 1
    mock_ws.accept.assert_called_once()
    assert mock_ws in manager.local_connections[room_id]
    # 驗證是否啟動了 Redis Listener Task
    mock_create_task.assert_called_once()
    
    # 模擬 Task 物件以便後續驗證 cancel
    mock_task_instance = MagicMock()
    manager.listener_tasks[room_id] = mock_task_instance

    # --- Act 2: Disconnect ---
    manager.disconnect(room_id, user_id, mock_ws)

    # Assert 2
    # 驗證連線被移除
    assert room_id not in manager.local_connections # 因為只有一個連線，移除後 key 應該被刪除
    # 驗證 Task 被取消
    mock_task_instance.cancel.assert_called_once()
    assert room_id not in manager.listener_tasks

@pytest.mark.asyncio
async def test_manager_broadcast_success(mocker):
    """
    測試：廣播訊息給本地連線
    驗證：bytes 解碼為 string 並透過 ws.send_text 發送
    """
    # Arrange
    room_id = "room_broadcast"
    
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    
    # 手動注入連線
    manager.local_connections[room_id] = {mock_ws1, mock_ws2}
    
    message_bytes = b"Hello World" # Redis 傳來的是 bytes

    # Act
    await manager.broadcast_to_local_clients(room_id, message_bytes)

    # Assert
    # 驗證兩個 WS 都收到了解碼後的文字訊息
    mock_ws1.send_text.assert_called_once_with("Hello World")
    mock_ws2.send_text.assert_called_once_with("Hello World")

@pytest.mark.asyncio
async def test_manager_broadcast_decode_error(mocker):
    """測試：解碼失敗時應記錄錯誤並略過 (不崩潰)"""
    room_id = "room_error"
    mock_ws = AsyncMock()
    manager.local_connections[room_id] = {mock_ws}
    
    # 無效的 utf-8 bytes
    invalid_bytes = b'\x80' 

    # Act
    await manager.broadcast_to_local_clients(room_id, invalid_bytes)

    # Assert
    # 應該不會呼叫 send_text，且程式不會拋出例外
    mock_ws.send_text.assert_not_called()

@pytest.mark.asyncio
async def test_manager_broadcast_send_error_cleanup(mocker):
    """測試：發送失敗時 (Client斷線)，應自動清理連線"""
    room_id = "room_cleanup"
    mock_ws_good = AsyncMock()
    mock_ws_bad = AsyncMock()
    
    # 模擬 ws_bad 發送時拋出例外
    mock_ws_bad.send_text.side_effect = Exception("Connection lost")
    
    manager.local_connections[room_id] = {mock_ws_good, mock_ws_bad}
    
    # Spy disconnect 方法
    spy_disconnect = mocker.spy(manager, 'disconnect')

    # Act
    await manager.broadcast_to_local_clients(room_id, b"msg")

    # Assert
    # Good ws 成功發送
    mock_ws_good.send_text.assert_called_once()
    # Bad ws 嘗試發送但失敗
    mock_ws_bad.send_text.assert_called_once()
    
    # 驗證是否呼叫 disconnect 清理 Bad ws
    spy_disconnect.assert_called_once_with(room_id, "[internal_cleanup]", mock_ws_bad)


@pytest.mark.asyncio
async def test_redis_listener_loop_cleanup(mocker):
    """測試：Redis listener 任務在被取消時應正確 unsubscribe 並關閉 client"""
    from app.services.message_service import manager

    room_id = "room_redis"

    class DummyPubSub:
        def __init__(self):
            self.subscribed = False
            self.unsubscribed = False

        async def subscribe(self, channel):
            self.subscribed = True

        async def get_message(self, ignore_subscribe_messages=True, timeout=None):
            # 模擬被取消以觸發 listener 的 CancelledError 分支
            raise asyncio.CancelledError()

        async def unsubscribe(self, channel):
            self.unsubscribed = True

    class DummyPubSubCtx:
        def __init__(self, pubsub):
            self._pubsub = pubsub

        async def __aenter__(self):
            return self._pubsub

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class DummyRedis:
        def __init__(self, pubsub):
            self._pubsub = pubsub
            self.closed = False

        def pubsub(self):
            return DummyPubSubCtx(self._pubsub)

        async def aclose(self):
            self.closed = True

    pubsub = DummyPubSub()
    dummy_redis = DummyRedis(pubsub)

    # patch aioredis.from_url to return our dummy redis client (synchronously)
    mocker.patch("app.services.message_service.aioredis.from_url", new=lambda *a, **kw: dummy_redis)

    # run the listener coroutine directly (it will exit when get_message raises CancelledError)
    await manager._redis_listener_loop(room_id)

    # assertions: subscribed then unsubscribed and client closed
    assert pubsub.subscribed is True
    assert pubsub.unsubscribed is True
    assert dummy_redis.closed is True

# ==========================================
# Part 9: 補強 get_user_rooms 的異常處理 (Line 180-182)
# ==========================================

@pytest.mark.asyncio
async def test_get_user_rooms_serialization_error(mock_db_session, mock_user_freelancer, mocker):
    """測試：Pydantic 序列化失敗時拋出 500"""
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    
    # 模擬 Repo 回傳了缺少必要欄位的物件 (例如缺 created_at)
    # 這會導致 RoomOut.model_validate 失敗
    bad_room = ChatRoom(room_id="r1") 
    mocker.patch.object(service.message_repo, 'get_rooms_by_user_id', return_value=[bad_room])

    with pytest.raises(HTTPException) as exc:
        await service.get_user_rooms(mock_user_freelancer)
    
    assert exc.value.status_code == 500
    assert "serialize" in exc.value.detail

# ==========================================
# Part 10: 補強權限檢查細節 (check_user_room_permission)
# ==========================================

@pytest.mark.asyncio
async def test_check_permission_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：檢查權限成功 (True)"""
    service = MessageService(mock_db_session, AsyncMock())
    mock_room = ChatRoom(participants=[ChatRoomParticipant(user_id=mock_user_freelancer.user_id)])
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)

    result = await service.check_user_room_permission("room_1", mock_user_freelancer)
    assert result is True

@pytest.mark.asyncio
async def test_check_permission_room_not_found(mock_db_session, mock_user_freelancer, mocker):
    """測試：檢查權限時房間不存在 (404)"""
    service = MessageService(mock_db_session, AsyncMock())
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.check_user_room_permission("room_404", mock_user_freelancer)
    assert exc.value.status_code == 404

# ==========================================
# Part 11: 補強建立聊天室邏輯 (Create Room)
# ==========================================

@pytest.mark.asyncio
async def test_create_chat_room_creator_is_invited(mock_db_session, mock_user_freelancer, mocker):
    """
    測試：創建者即為被邀請者 (例如工作者點擊雇主 Say Hi，反向邏輯)
    代碼路徑：elif creator.user_id == invited_id:
    """
    service = MessageService(mock_db_session, AsyncMock())
    
    # 假設專案是雇主的
    employer_id = "boss_1"
    mock_project = Project(project_id="p1", employer_id=employer_id)
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=mock_project)
    mocker.patch.object(service.message_repo, 'find_room_by_participants', return_value=None)
    
    # Mock Create
    mock_new_room = ChatRoom(room_id="new_room", created_at=datetime.now())
    mock_create = mocker.patch.object(service.message_repo, 'create_room_and_participants', return_value=mock_new_room)

    # Act: 工作者 (freelancer) 邀請 自己 (freelancer) -> 其實是想跟雇主聊
    # 這會觸發 logic: participant_ids_list = [employer_id, creator.user_id]
    room_data = RoomCreate(project_id="p1", invited_user_id=mock_user_freelancer.user_id)
    await service.create_chat_room(room_data, mock_user_freelancer)

    # Assert
    # 驗證參與者是否為 [employer_id, freelancer_id]
    call_args = mock_create.call_args[1]
    participants = call_args['participant_ids']
    assert set(participants) == {employer_id, mock_user_freelancer.user_id}

@pytest.mark.asyncio
async def test_create_chat_room_project_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：建立聊天室時專案不存在"""
    service = MessageService(mock_db_session, AsyncMock())
    mocker.patch.object(service.project_repo, 'get_project_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.create_chat_room(RoomCreate(project_id="p_404"), mock_user_employer)
    assert exc.value.status_code == 404

# ==========================================
# Part 12: 補強 WebSocket JSON 解析錯誤
# ==========================================

@pytest.mark.asyncio
async def test_handle_websocket_message_json_error(mock_db_session, mocker):
    """測試：WebSocket 收到無效 JSON"""
    service = MessageService(mock_db_session, AsyncMock())
    
    # 壞掉的 JSON
    bad_data = "{'content': 'oops', no_quote_key}" 
    
    with pytest.raises(ValueError) as exc:
        await service.handle_websocket_message("r1", "u1", bad_data)
    
    assert "Message processing error" in str(exc.value)
    # 驗證有紀錄 error log (透過 mock_db_session rollback 側面印證進入了 except block)
    mock_db_session.rollback.assert_called_once()

# ==========================================
# Part 13: 補強 WebSocket 處理邊界案例 (提升 MessageService 覆蓋率)
# ==========================================

@pytest.mark.asyncio
async def test_handle_websocket_message_no_sender_info(mock_db_session, mocker):
    """
    測試：儲存訊息後，如果 new_message.sender 為 None (Repo 失敗/未載入)，
    通知標題應該使用「某人」來避免崩潰。
    (覆蓋 new_message.sender else "某人" 分支)
    """
    # Arrange
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    room_id = "room_1_no_sender"
    sender_id = "sender_1"
    raw_data = json.dumps({"content": "Hello World", "content_type": "text"})
    
    mock_room = ChatRoom(
        room_id=room_id, 
        project=Project(title="Proj"),
        participants=[ChatRoomParticipant(user_id="receiver_1")]
    )
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    
    # Mock saved message, but explicitly set sender to None 
    mock_saved_msg = Message(
        message_id="msg_new",
        room_id=room_id,
        sender_id=sender_id,
        content="Hello World", 
        content_type="text",
        is_read=False,
        created_at=datetime.now(),
        sender=None # <-- 關鍵：模擬 sender 載入失敗
    )
    mocker.patch.object(service.message_repo, 'save_message', return_value=mock_saved_msg)
    mocker.patch.object(mock_db_session, 'refresh', new_callable=AsyncMock)
    
    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    # Act
    await service.handle_websocket_message(room_id, sender_id, raw_data)

    # Assert
    mock_notify.assert_called_once()
    assert "某人" in mock_notify.call_args[1]['message'] # 驗證使用了「某人」
    mock_redis.publish.assert_called_once()


@pytest.mark.asyncio
async def test_handle_websocket_message_single_participant(mock_db_session, mocker):
    """
    測試：聊天室只有一個參與者 (發送者自己)，不應發送通知
    (覆蓋 if p.user_id != sender_id: 判斷為 False 的分支)
    """
    # Arrange
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    room_id = "room_1_single"
    sender_id = "sender_1"
    raw_data = json.dumps({"content": "Hello World", "content_type": "text"})
    
    # 房間只有發送者自己
    mock_room = ChatRoom(
        room_id=room_id, 
        project=Project(title="Proj"),
        participants=[ChatRoomParticipant(user_id=sender_id)] # <-- 關鍵：只有一個參與者
    )
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)
    
    # Mock sender User object
    mock_sender_user = User(user_id=sender_id, email="s@test.com", role="自由工作者", is_active=True)
    mock_saved_msg = Message(
        message_id="msg_new", room_id=room_id, sender_id=sender_id,
        content="Hello World", content_type="text", is_read=False, created_at=datetime.now(),
        sender=mock_sender_user
    )
    mocker.patch.object(service.message_repo, 'save_message', return_value=mock_saved_msg)
    mocker.patch.object(mock_db_session, 'refresh', new_callable=AsyncMock)

    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    # Act
    await service.handle_websocket_message(room_id, sender_id, raw_data)

    # Assert
    # 驗證通知沒有被呼叫
    mock_notify.assert_not_called()
    mock_redis.publish.assert_called_once() # Publish 還是要發送，確保即時通訊正常


@pytest.mark.asyncio
async def test_manager_disconnect_no_room_does_not_raise():
    """Calling disconnect for a non-existent room should not raise."""
    from app.services.message_service import manager

    room_id = "no_such_room"
    # Ensure clean state
    if room_id in manager.local_connections:
        del manager.local_connections[room_id]
    if room_id in manager.listener_tasks:
        del manager.listener_tasks[room_id]

    fake_ws = MagicMock()
    # Should not raise
    manager.disconnect(room_id, "u1", fake_ws)


@pytest.mark.asyncio
async def test_manager_connect_idempotent(mocker):
    """If a listener task already exists, connect should not start a new one."""
    from app.services.message_service import manager

    room_id = "idempotent_room"
    user_id = "u1"
    mock_ws = AsyncMock()

    # clean state
    if room_id in manager.local_connections:
        del manager.local_connections[room_id]
    # pre-create a listener task
    manager.listener_tasks[room_id] = MagicMock()

    mock_create = mocker.patch("asyncio.create_task")
    await manager.connect(room_id, user_id, mock_ws)

    # since listener_tasks already had an entry, create_task should not be called
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_redis_listener_exception_closes_client(mocker):
    """If the redis listener raises, it unsubscribes and closes client."""
    from app.services.message_service import manager

    room_id = "room_exc"

    class DummyPubSub:
        def __init__(self):
            self.subscribed = False
            self.unsubscribed = False

        async def subscribe(self, channel):
            self.subscribed = True

        async def get_message(self, ignore_subscribe_messages=True, timeout=None):
            # raise generic exception to exercise except branch
            raise Exception("boom")

        async def unsubscribe(self, channel):
            self.unsubscribed = True

    class DummyPubSubCtx:
        def __init__(self, pubsub):
            self._pubsub = pubsub

        async def __aenter__(self):
            return self._pubsub

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class DummyRedis:
        def __init__(self, pubsub):
            self._pubsub = pubsub
            self.closed = False

        def pubsub(self):
            return DummyPubSubCtx(self._pubsub)

        async def aclose(self):
            self.closed = True

    pubsub = DummyPubSub()
    dummy_redis = DummyRedis(pubsub)

    mocker.patch("app.services.message_service.aioredis.from_url", new=lambda *a, **kw: dummy_redis)

    await manager._redis_listener_loop(room_id)

    assert pubsub.subscribed is True
    assert pubsub.unsubscribed is True
    assert dummy_redis.closed is True


@pytest.mark.asyncio
async def test_handle_websocket_message_multiple_receivers_triggers_multiple_notifications(mock_db_session, mocker):
    """When multiple participants aside from sender exist, notifications should be sent to each."""
    mock_redis = AsyncMock()
    service = MessageService(mock_db_session, mock_redis)
    room_id = "room_multi"
    sender_id = "sender_1"
    raw_data = json.dumps({"content": "Hello All", "content_type": "text"})

    mock_room = ChatRoom(
        room_id=room_id,
        project=Project(title="Proj"),
        participants=[
            ChatRoomParticipant(user_id=sender_id),
            ChatRoomParticipant(user_id="r1"),
            ChatRoomParticipant(user_id="r2")
        ]
    )
    mocker.patch.object(service.message_repo, 'get_room_by_id_with_participants', return_value=mock_room)

    mock_sender_user = User(user_id=sender_id, email="s@test.com", role="自由工作者", is_active=True)
    mock_saved_msg = Message(
        message_id="m1", room_id=room_id, sender_id=sender_id,
        content="Hello All", content_type="text", is_read=False, created_at=datetime.now(), sender=mock_sender_user
    )
    mocker.patch.object(service.message_repo, 'save_message', return_value=mock_saved_msg)
    mocker.patch.object(mock_db_session, 'refresh', new_callable=AsyncMock)

    mock_notify = mocker.patch.object(service.notification_service, 'create_notification', new_callable=AsyncMock)

    await service.handle_websocket_message(room_id, sender_id, raw_data)

    # two notifications for r1 and r2
    assert mock_notify.call_count == 2
    mock_redis.publish.assert_called_once()