# app/services/message_service.py

# --- 1. 匯入 (完整) ---
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Set, Tuple
import logging
import json
import asyncio
from collections import defaultdict
import redis.asyncio as aioredis

# (匯入 Schema, Repo, Model...)
from app.schemas.message_schema import RoomCreate, MessageOut, MessageIn, RoomOut, ParticipantOut
from app.schemas.user_schema import UserOut
from app.repositories.message_repo import MessageRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.proposal_repo import ProposalRepository
from app.models.user import User
from app.models.message import ChatRoom, Message, ChatRoomParticipant
from app.models.project import Project
from app.services.notification_service import NotificationService

# (修改) 移除 redis_manager 的匯入，改為匯入 settings
# (REMOVED) from app.core.redis import redis_manager
from app.core.config import settings # (新增) 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 2. ConnectionManager (修正) ---

class ConnectionManager:
    def __init__(self):
        self.local_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.listener_tasks: Dict[str, asyncio.Task] = {}
        
        # (REMOVED) 移除共享的 redis_sub_client
        # self.redis_sub_client: aioredis.Redis | None = None

    # (REMOVED) 移除 _get_subscriber_client，因為不再共享
    # async def _get_subscriber_client(self) -> aioredis.Redis: ...

    async def connect(self, room_id: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.local_connections[room_id].add(websocket)
        logger.info(f"User {user_id} connected to Room {room_id} (local instance). Total local: {len(self.local_connections[room_id])}")

        if room_id not in self.listener_tasks:
            logger.info(f"Starting Redis listener task for Room {room_id} on this instance...")
            # (保持不變) 啟動背景任務
            task = asyncio.create_task(
                self._redis_listener_loop(room_id)
            )
            self.listener_tasks[room_id] = task

    def disconnect(self, room_id: str, user_id: str, websocket: WebSocket):
        # (保持不變，邏輯正確)
        try:
            self.local_connections[room_id].remove(websocket)
            logger.info(f"User {user_id} disconnected from Room {room_id} (local instance). Remaining local: {len(self.local_connections[room_id])}")
            
            if not self.local_connections[room_id]:
                logger.info(f"Stopping Redis listener task for Room {room_id} (last local connection closed)...")
                if room_id in self.listener_tasks:
                    task = self.listener_tasks.pop(room_id)
                    task.cancel()
                if room_id in self.local_connections:
                    del self.local_connections[room_id]
                    
        except (KeyError, ValueError):
            pass

    async def _redis_listener_loop(self, room_id: str):
        """
        (修正)
        此任務現在會建立並管理「自己專屬」的 Redis 連線。
        """
        channel_name = f"chat:{room_id}"
        pubsub = None
        
        # (新增) 建立此任務專屬的 Redis 客戶端
        redis_client = None
        try:
            # 1. (修改) 建立一個新的、獨立的連線
            redis_client = aioredis.from_url(
                settings.REDIS_URL, 
                decode_responses=False
            )
            
            # 2. 建立 PubSub 物件
            async with redis_client.pubsub() as pubsub:
                await pubsub.subscribe(channel_name)
                logger.info(f"Subscribed to Redis channel: {channel_name}")
                
                # 3. 進入監聽迴圈 (保持不變)
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
                    
                    if message and message["type"] == "message":
                        message_data_bytes = message["data"]
                        await self.broadcast_to_local_clients(room_id, message_data_bytes)
                        
        except asyncio.CancelledError:
            logger.info(f"Listener task for {channel_name} was cancelled (graceful stop).")
        except Exception as e:
            logger.error(f"Redis listener for {channel_name} failed: {e}", exc_info=True)
        finally:
            # 5. 清理 (保持不變，但很重要)
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel_name)
                    logger.info(f"Unsubscribed from Redis channel: {channel_name}")
                except Exception as e:
                    logger.error(f"Error unsubscribing {channel_name}: {e}")
            
            # (新增) 關閉此任務專屬的客戶端連線
            if redis_client:
                await redis_client.aclose()
                logger.info(f"Closed dedicated Redis client for {channel_name}")

            if room_id in self.listener_tasks:
                del self.listener_tasks[room_id]
                logger.info(f"Listener task for {room_id} fully cleaned up.")

    async def broadcast_to_local_clients(self, room_id: str, message_data: bytes):
        """
        (修正)
        將從 Redis 收到的訊息 (bytes) 解碼 (decode) 為 string，
        並使用 send_text 傳送給所有本地連線的客戶端。
        """
        if room_id in self.local_connections:
            
            # (新增) 將 bytes 解碼回 UTF-8 字串
            try:
                message_string = message_data.decode('utf-8')
            except UnicodeDecodeError:
                logger.error(f"無法解碼來自 Redis 的訊息 (Room: {room_id})")
                return

            disconnected_clients = []
            for ws in list(self.local_connections[room_id]):
                try:
                    # (修改) 從 send_bytes 改為 send_text
                    await ws.send_text(message_string)
                except Exception:
                    disconnected_clients.append(ws)
            
            # (保持不變) 清理已斷開的連線
            for ws in disconnected_clients:
                self.disconnect(room_id, "[internal_cleanup]", ws)

# (保持不變) 實例化管理器
manager = ConnectionManager()

# --- 3. MessageService (保持不變) ---
# (您在上一提示中提供的 REST API 邏輯 + Redis Publish 邏輯是正確的)

class MessageService:
    def __init__(
        self, 
        db: AsyncSession,
        redis_client: aioredis.Redis
    ):
        self.db = db
        self.redis = redis_client
        self.message_repo = MessageRepository(db)
        self.project_repo = ProjectRepository(db)
        self.proposal_repo = ProposalRepository(db)
        self.notification_service = NotificationService(db)

    # --- ( REST API 相關方法 - 保持不變 ) ---
    
    async def get_user_rooms(self, user: User) -> List[RoomOut]:
        # (來自 services.md)
        rooms = await self.message_repo.get_rooms_by_user_id(user.user_id)
        try:
            rooms_out = [RoomOut.model_validate(room) for room in rooms]
            return rooms_out
        except Exception as e:
            logger.error(f"Pydantic validation error in get_user_rooms: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to serialize rooms")
    
    async def create_chat_room(self, room_data: RoomCreate, creator: User) -> RoomOut:
        # (來自上一輪的修正)
        project_id = room_data.project_id
        invited_id = room_data.invited_user_id
        
        project = await self.project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="案件不存在")

        employer_id = project.employer_id

        if creator.user_id == employer_id:
            if not invited_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="雇主邀請時必須指定 invited_user_id")
            participant_ids_list = [employer_id, invited_id]
        elif creator.user_id == invited_id:
            participant_ids_list = [employer_id, creator.user_id]
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="無權限創建此案件的聊天室")

        # (Bug Fix) 去重
        participant_ids = list(set(participant_ids_list))
        if len(participant_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無法與自己建立聊天室。參與者ID重複。"
            )
            
        # (新需求) 移除提案限制 (已移除)
        
        existing_room = await self.message_repo.find_room_by_participants(project_id, participant_ids)
        if existing_room:
            return RoomOut.model_validate(existing_room)

        try:
            new_room = await self.message_repo.create_room_and_participants(
                project_id=project_id,
                participant_ids=participant_ids
            )
            await self.db.commit()
            
            await self.db.refresh(new_room)
            if new_room.participants:
                 for p in new_room.participants:
                    await self.db.refresh(p)
            
            return RoomOut.model_validate(new_room)
        except Exception as e:
            await self.db.rollback()
            logger.error(f"聊天室建立失敗: {str(e)}", exc_info=True)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"聊天室建立失敗: {str(e)}")

    async def check_user_room_permission(self, room_id: str, user: User) -> bool:
        # (來自 services.md)
        room = await self.message_repo.get_room_by_id_with_participants(room_id)
        if not room:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="聊天室不存在")
        participant_ids = {p.user_id for p in room.participants}
        if user.user_id not in participant_ids:
            return False
        return True
    
    async def get_room_messages(self, room_id: str, user: User) -> List[MessageOut]:
        # (來自 services.md)
        if not await self.check_user_room_permission(room_id, user):
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="無權限查看此聊天室")
        try:
            await self.message_repo.mark_messages_as_read(room_id, user.user_id)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"標記已讀失敗: {e}")
        
        messages = await self.message_repo.get_messages_by_room_id(room_id)
        return [MessageOut.model_validate(msg) for msg in messages]
    
    
    # --- WebSocket 核心 (保持不變) ---

    async def handle_websocket_message(
        self,
        room_id: str,
        sender_id: str,
        message_data: str
    ) -> None:
        # (來自 services.md，邏輯正確)
        room = None
        try:
            data_dict = json.loads(message_data)
            message_in = MessageIn(room_id=room_id, **data_dict)

            room = await self.message_repo.get_room_by_id_with_participants(room_id)
            if not room:
                raise ValueError(f"Room {room_id} not found")

            new_message = await self.message_repo.save_message(
                room_id=room_id,
                sender_id=sender_id,
                content=message_in.content,
                content_type=message_in.content_type
            )
            
            await self.db.commit()
            await self.db.refresh(new_message)
            
            # (M8.3 通知)
            sender_name = new_message.sender.email.split('@')[0] if new_message.sender else "某人"
            project_title = room.project.title if room.project else "聊天室"
            notification_title = f"您在「{project_title}」中有新訊息"
            notification_msg = f"{sender_name} 說：{message_in.content[:30]}..."
            link_url = "/chat"
            for p in room.participants:
                if p.user_id != sender_id:
                    await self.notification_service.create_notification(
                        user_id=p.user_id,
                        title=notification_title,
                        message=notification_msg,
                        link_url=link_url
                    )

            # (轉換)
            message_out = MessageOut.model_validate(new_message)
            broadcast_msg_bytes = message_out.model_dump_json().encode('utf-8')

            # (Publish)
            channel_name = f"chat:{room_id}"
            await self.redis.publish(channel_name, broadcast_msg_bytes)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error handling message: {e}", exc_info=True)
            raise ValueError(f"Message processing error: {e}")