# app/services/message_service.py
# (我們將移除 _create_system_message 並簡化 create_chat_room)

from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Tuple
import logging
import json

# 匯入 Schemas
from app.schemas.message_schema import RoomCreate, MessageOut, MessageIn, RoomOut, ParticipantOut
from app.schemas.user_schema import UserOut

# 匯入 Repositories
from app.repositories.message_repo import MessageRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.proposal_repo import ProposalRepository

from app.models.user import User
from app.models.message import ChatRoom, Message, ChatRoomParticipant

# 匯入 NotificationService 以便使用
from app.services.notification_service import NotificationService 


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. WebSocket 連線管理器 (保持不變) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[Tuple[str, WebSocket]]] = {}

    async def connect(self, room_id: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append((user_id, websocket))
        logger.info(f"User {user_id} connected to Room {room_id}.")

    def disconnect(self, room_id: str, user_id: str, websocket: WebSocket):
        try:
            connection_tuple = (user_id, websocket)
            if room_id in self.active_connections and connection_tuple in self.active_connections[room_id]:
                self.active_connections[room_id].remove(connection_tuple)
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]
            logger.info(f"User {user_id} disconnected from Room {room_id}.")
        except (ValueError, KeyError):
            pass

    async def broadcast_message(self, room_id: str, message_json: str):
        """將 JSON 字串訊息廣播給特定 Room 的所有連線。"""
        if room_id in self.active_connections:
            disconnected_clients = []
            for connection in self.active_connections[room_id]:
                user_id, ws = connection
                try:
                    await ws.send_text(message_json)
                except Exception as e:
                    logger.warning(f"Failed to send message to client {user_id} in room {room_id}: {e}")
                    disconnected_clients.append(connection)
            # 清理已斷開的連線
            for client in disconnected_clients:
                self.disconnect(room_id, client[0], client[1])

# 實例化管理器 (全域單例)
manager = ConnectionManager()

# --- 2. MessageService 業務邏輯 ---

class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.message_repo = MessageRepository(db)
        self.project_repo = ProjectRepository(db)
        self.proposal_repo = ProposalRepository(db)
        self.notification_service = NotificationService(db) 

    async def get_user_rooms(self, user: User) -> List[RoomOut]:
        """
        獲取使用者的所有聊天室 (REST API 用)。
        (已優化為返回 RoomOut)
        """
        rooms = await self.message_repo.get_rooms_by_user_id(user.user_id)
        # --- (必要修正) ---
        # 不要手動建立 RoomOut，
        # 讓 Pydantic 從 ORM 物件自動驗證並填充所有欄位 (包含 project)
        try:
            rooms_out = [RoomOut.model_validate(room) for room in rooms]
            return rooms_out
        except Exception as e:
            # 處理 Pydantic 驗證錯誤
            logger.error(f"Pydantic validation error in get_user_rooms: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to serialize rooms")
        # --- (修正結束) ---
        

    async def create_chat_room(self, room_data: RoomCreate, creator: User) -> RoomOut:
        """
        業務邏輯：創建聊天室 (REST API 用)。
        規則 M8.1: 聊天室必須在「提案被接受」或「雇主主動邀請」後才能建立。
        """
        project_id = room_data.project_id
        invited_id = room_data.invited_user_id
        project = await self.project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="案件不存在")

        employer_id = project.employer_id
        # 確定參與者
        if creator.user_id == employer_id:
            if not invited_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="雇主邀請時必須指定 invited_user_id")
            participant_ids = [employer_id, invited_id]
            freelancer_id = invited_id
        elif creator.user_id == invited_id:
            participant_ids = [employer_id, invited_id]
            freelancer_id = creator.user_id
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="無權限創建此案件的聊天室")
        
        # 驗證 M8.1 業務規則：
        proposal = await self.proposal_repo.check_existing_proposal(project_id, freelancer_id)
        if not proposal or proposal.status != "已接受":
            # (未來可擴充 M5 邏輯：如果雇主是 '主動邀請'，則允許建立)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="聊天室只能在提案被接受後建立。"
            )

        # 檢查聊天室是否已存在
        existing_room = await self.message_repo.find_room_by_participants(project_id, participant_ids)
        if existing_room:
            # 如果已存在，直接返回該聊天室
            return RoomOut.model_validate(existing_room)
        
        try:
            # (修正) 步驟 1: 建立房間 (但不 Commit)
            new_room = await self.message_repo.create_room_and_participants(
                project_id=project_id,
                participant_ids=participant_ids
            )
            
            # (修正) 步驟 2: 移除 _create_system_message 呼叫
            # (移除) await self._create_system_message(...)

            # (修正) 步驟 3: 一次性 Commit
            await self.db.commit()

            # (修正) 步驟 4: Commit 成功後，手動 refresh 剛才 eager load 的物件
            # 這是為了確保 Pydantic 驗證時能抓到最新的資料
            await self.db.refresh(new_room)
            # 確保 participants 也被 refresh (如果需要)
            for p in new_room.participants:
                await self.db.refresh(p)
            
            return RoomOut.model_validate(new_room)
        
        except Exception as e:
            await self.db.rollback()
            logger.error(f"聊天室建立失敗: {str(e)}", exc_info=True)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"聊天室建立失敗: {str(e)}")

    # (修正) 移除 _create_system_message 輔助函式

    async def check_user_room_permission(self, room_id: str, user: User) -> bool:
        """
        (M8.1 安全) 檢查使用者是否有權限進入此聊天室 (WS 驗證用)
        """
        room = await self.message_repo.get_room_by_id_with_participants(room_id)
        if not room:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="聊天室不存在")
        participant_ids = {p.user_id for p in room.participants}
        if user.user_id not in participant_ids:
            return False
        return True

    async def get_room_messages(self, room_id: str, user: User) -> List[MessageOut]:
        """
        獲取歷史訊息，並執行標記已讀操作 (REST API 用)。
        (已優化為返回 MessageOut)
        """
        if not await self.check_user_room_permission(room_id, user):
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="無權限查看此聊天室")
        try:
            await self.message_repo.mark_messages_as_read(room_id, user.user_id)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"標記已讀失敗: {e}")
            # (繼續執行)
        messages = await self.message_repo.get_messages_by_room_id(room_id)
        # (修正) 將 ORM 轉換為 Pydantic Schema
        return [MessageOut.model_validate(msg) for msg in messages]

    async def handle_websocket_message(
        self,
        room_id: str,
        sender_id: str,
        message_data: str 
    ) -> None:
        """
        處理 WebSocket 接收到的訊息：儲存、廣播、並觸發通知。
        """
        
        # --- (M8.3 修正：為通知載入額外資訊) ---
        room = None
        try:
            # 1. 驗證訊息
            data_dict = json.loads(message_data)
            message_in = MessageIn(room_id=room_id, **data_dict) 

            # 2. (新) 獲取聊天室資訊 (包含 project 和 participants)
            room = await self.message_repo.get_room_by_id_with_participants(room_id)
            if not room:
                raise ValueError(f"Room {room_id} not found")

            # 3. 儲存訊息 (Repo 會 Eager Load sender)
            new_message = await self.message_repo.save_message(
                room_id=room_id,
                sender_id=sender_id,
                content=message_in.content,
                content_type=message_in.content_type
            )
            
            # 4. 提交事務 (Commit)
            await self.db.commit()
            
            # 5. (新) 觸發通知 (在 Commit 之後)
            # (我們需要 refresh new_message 才能安全地存取 sender)
            await self.db.refresh(new_message) 

            # --- (M8.3 邏輯開始) ---
            sender_name = new_message.sender.email.split('@')[0] if new_message.sender else "某人"
            project_title = room.project.title if room.project else "聊天室" #
            
            notification_title = f"您在「{project_title}」中有新訊息"
            notification_msg = f"{sender_name} 說：{message_in.content[:30]}..."
            # 連結到聊天室
            link_url = "/chat" 
            
            for p in room.participants: #
                if p.user_id != sender_id: # 只通知其他人
                    await self.notification_service.create_notification(
                        user_id=p.user_id,
                        title=notification_title,
                        message=notification_msg,
                        link_url=link_url
                    )
            # --- (M8.3 邏輯結束) ---

            # 6. 轉換為 Pydantic Model (用於廣播)
            message_out = MessageOut.model_validate(new_message)
            broadcast_msg = message_out.model_dump_json()

            # 7. 廣播訊息
            await manager.broadcast_message(room_id, broadcast_msg)
        
        except Exception as e:
            # (保持不變) 錯誤處理
            await self.db.rollback()
            logger.error(f"Error handling message: {e}", exc_info=True)
            raise ValueError(f"Message processing error: {e}")