# app/routers/message_router.py

from fastapi import APIRouter, Depends, status, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_from_websocket_token
from app.services.message_service import MessageService, manager
from app.schemas.message_schema import RoomCreate, RoomOut, MessageOut
from app.models.user import User
from typing import List
import logging

router = APIRouter(prefix="/messages", tags=["Messaging"])

# --- RESTful API ---

@router.get("/rooms", response_model=List[RoomOut], summary="獲取使用者的聊天室列表")
async def list_user_rooms(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.1) 獲取當前登入使用者參與的所有聊天室列表。
    (已包含 Eager Loading 優化)
    """
    service = MessageService(db)
    rooms = await service.get_user_rooms(user)
    # Service 層的 Repo 已 Eager Load participants 和 user
    return rooms

@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED, summary="創建新聊天室")
async def create_room(
    room_data: RoomCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.1) 根據業務規則 (如提案被接受) 創建聊天室。
    """
    service = MessageService(db)
    room = await service.create_chat_room(room_data, user)
    return room

@router.get("/{room_id}/messages", response_model=List[MessageOut], summary="獲取聊天室的歷史訊息")
async def get_history_messages(
    room_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.2) 獲取聊天室的歷史訊息 (最多50條)。
    (API 會自動將未讀訊息標記為已讀)
    """
    service = MessageService(db)
    messages = await service.get_room_messages(room_id, user)
    # Repo 已 Eager Load sender 並按 (舊 -> 新) 排序
    return messages


# --- WebSocket Endpoint ---

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: str, 
    # 【安全修正】使用依賴注入從 Token 獲取 User
    # 前端連線 URL 必須是: /ws/{room_id}?token=...
    user: User = Depends(get_current_user_from_websocket_token),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.2) WebSocket 即時通訊端點。
    - 連線 URL: /ws/{room_id}?token=<JWT_TOKEN>
    """
    
    service = MessageService(db)
    
    # 1. 驗證連線權限
    try:
        is_participant = await service.check_user_room_permission(room_id, user)
        if not is_participant:
            # 如果驗證失敗，關閉連線
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not authorized")
            return
    except HTTPException:
         await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found or user unauthorized")
         return

    # 2. 建立連線
    await manager.connect(room_id, user.user_id, websocket)
    
    try:
        while True:
            # 接收前端訊息 (JSON 字串)
            data = await websocket.receive_text()
            
            # 3. 處理訊息：儲存到 DB 並廣播
            try:
                # 這裡調用 Service 處理持久化和廣播
                await service.handle_websocket_message(room_id, user.user_id, data)
                
            except Exception as e:
                # 如果儲存或廣播失敗，給單一使用者發送錯誤訊息
                logging.error(f"Error handling message in room {room_id}: {e}")
                error_msg = {"type": "error", "content": f"Message processing failed: {str(e)}"}
                await websocket.send_json(error_msg)
                
    except WebSocketDisconnect:
        # 4. 斷開連線
        manager.disconnect(room_id, user.user_id, websocket)
        # (可選) 廣播離線通知
        # await manager.broadcast_message(room_id, f"User {user_id} left the chat.")
    except Exception as e:
        # 處理意外錯誤
        logging.error(f"Unexpected error in WS {room_id} for user {user.user_id}: {e}")
        manager.disconnect(room_id, user.user_id, websocket)