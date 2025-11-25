# app/routers/message_router.py

from fastapi import APIRouter, Depends, status, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_from_websocket_token
from app.services.message_service import MessageService, manager # (保持不變)
from app.schemas.message_schema import RoomCreate, RoomOut, MessageOut
from app.models.user import User
from typing import List
import logging

# --- (M8.1 重構 新增) ---
# 匯入 Redis 依賴 (來自步驟二)
import redis.asyncio as aioredis
from app.core.redis import get_redis
# --- (修改結束) ---

router = APIRouter(prefix="/messages", tags=["Messaging"])

# --- RESTful API (修改) ---

@router.get("/rooms", response_model=List[RoomOut], summary="獲取使用者的聊天室列表")
async def list_user_rooms(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # (新增) 注入 Redis (用於 Publish)
    redis_client: aioredis.Redis = Depends(get_redis) 
):
    """
    (M8.1) 獲取當前登入使用者參與的所有聊天室列表。
    (已包含 Eager Loading 優化)
    """
    # (修改) 傳入 redis_client
    service = MessageService(db, redis_client)
    rooms = await service.get_user_rooms(user)
    return rooms

@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED, summary="創建新聊天室")
async def create_room(
    room_data: RoomCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # (新增) 注入 Redis (用於 Publish)
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    (M8.1) 根據業務規則 (如提案被接受) 創建聊天室。
    """
    # (修改) 傳入 redis_client
    service = MessageService(db, redis_client)
    room = await service.create_chat_room(room_data, user)
    return room

@router.get("/{room_id}/messages", response_model=List[MessageOut], summary="獲取聊天室的歷史訊息")
async def get_history_messages(
    room_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # (新增) 注入 Redis (用於 Publish)
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    (M8.2) 獲取聊天室的歷史訊息 (最多50條)。
    (API 會自動將未讀訊息標記為已讀)
    """
    # (修改) 傳入 redis_client
    service = MessageService(db, redis_client)
    messages = await service.get_room_messages(room_id, user)
    return messages


# --- WebSocket Endpoint (修改) ---

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: str, 
    user: User = Depends(get_current_user_from_websocket_token),
    db: AsyncSession = Depends(get_db),
    
    # (新增) 
    # 僅需注入用於「發布 (PUBLISH)」的 Redis Client
    # 「訂閱 (SUBSCRIBE)」的 Client 由 manager 內部管理
    redis_publish_client: aioredis.Redis = Depends(get_redis)
):
    """
    (M8.2) WebSocket 即時通訊端點 (已重構為 Stateless)。
    - 連線 URL: /ws/{room_id}?token=<JWT_TOKEN>
    """
    
    # (修改) 
    # 建立 Service 實例 (用於 PUBLISH)
    service = MessageService(db, redis_publish_client)
    
    # 1. 驗證連線權限 (保持不變)
    try:
        is_participant = await service.check_user_room_permission(room_id, user)
        if not is_participant:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not authorized")
            return
    except HTTPException:
         await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found or user unauthorized")
         return

    # 2. 建立連線 (保持不變)
    # 呼叫 manager.connect (來自步驟三的重構版本)
    # 它會自動將 WS 加入「本地」Set，並在需要時啟動 Redis 訂閱任務
    await manager.connect(room_id, user.user_id, websocket)
    
    try:
        while True:
            # 接收前端訊息 (JSON 字串)
            data = await websocket.receive_text()
            
            # 3. 處理訊息：儲存到 DB 並「發布 (PUBLISH)」到 Redis
            try:
                # 呼叫 service.handle_websocket_message (來自步驟三的重構版本)
                await service.handle_websocket_message(room_id, user.user_id, data)
                
            except Exception as e:
                # (保持不變)
                logging.error(f"Error handling message in room {room_id}: {e}")
                error_msg = {"type": "error", "content": f"Message processing failed: {str(e)}"}
                await websocket.send_json(error_msg)
                
    except WebSocketDisconnect:
        # 4. 斷開連線 (保持不變)
        logging.info(f"WS disconnected (Graceful): User {user.user_id} from Room {room_id}")
    except Exception as e:
        # 處理意外錯誤 (保持不變)
        logging.error(f"Unexpected error in WS {room_id} for user {user.user_id}: {e}")
    finally:
        # 5. 斷開連線 (保持不變)
        # 呼叫 manager.disconnect (來自步驟三的重構版本)
        # 它會自動將 WS 從「本地」Set 移除，並在需要時取消 Redis 訂閱任務
        manager.disconnect(room_id, user.user_id, websocket)