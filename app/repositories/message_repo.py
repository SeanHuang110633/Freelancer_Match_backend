# app/repositories/message_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List
import uuid

# (新增) 匯入 Project，以便在 joinedload 中使用
from app.models.message import ChatRoom, ChatRoomParticipant, Message
from app.models.user import User
from app.models.project import Project 
from app.models.employer_profile import EmployerProfile # <-- (新增)

class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- ChatRoom 相關操作 ---

    async def get_room_by_id_with_participants(self, room_id: str) -> Optional[ChatRoom]:
        stmt = (
            select(ChatRoom)
            .where(ChatRoom.room_id == room_id)
            .options(
                selectinload(ChatRoom.participants), # 載入參與者
                # --- (8.3) ---
                # 同時載入關聯的 Project 物件
                joinedload(ChatRoom.project, innerjoin=False) #
                # --- (修正結束) ---
            )
        )
            
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # --- (必要修正) ---
    async def get_rooms_by_user_id(self, user_id: str) -> List[ChatRoom]:
        """
        獲取使用者參與的所有聊天室，並 Eager Load 關聯資料。
        """
        # 1. 找到使用者參與的所有 ChatRoomParticipant 紀錄
        participants_stmt = (
            select(ChatRoomParticipant)
            .where(ChatRoomParticipant.user_id == user_id)
            .options(
                # (重要：修正 Bug 3) 
                # 建立第一個查詢鏈:
                # Participant -> Room -> Project -> Employer -> EmployerProfile
                joinedload(ChatRoomParticipant.room)
                    .joinedload(ChatRoom.project, innerjoin=False)
                    .options( # <-- (新增巢狀 options)
                        joinedload(Project.employer).
                        selectinload(User.employer_profile)
                    ),
                
                # (修正) 建立第二個查詢鏈: 
                # Participant -> Room -> All Participants -> Participant's User
                joinedload(ChatRoomParticipant.room)
                    .selectinload(ChatRoom.participants) #
                    .selectinload(ChatRoomParticipant.user)
            )
        )
        # --- (修正結束) ---

        participant_records = (await self.db.execute(participants_stmt)).scalars().all()
        
        # 2. 提取獨一無二的 ChatRoom 物件
        # (因為 Eager Loading，這裡的 room 物件將包含 .project 和 .participants)
        rooms = list({p.room for p in participant_records if p.room})
        
        rooms.sort(key=lambda r: r.created_at, reverse=True)
        return rooms

    async def find_room_by_participants(self, project_id: str, participant_ids: List[str]) -> Optional[ChatRoom]:
        # (保持不變)
        stmt = (
            select(ChatRoom)
            .where(ChatRoom.context_project_id == project_id)
            .options(selectinload(ChatRoom.participants))
        )
        rooms = (await self.db.execute(stmt)).scalars().all()
        participant_set = set(participant_ids)
        for room in rooms:
            room_participant_set = {p.user_id for p in room.participants}
            if room_participant_set == participant_set:
                return room
        return None

    async def create_room_and_participants(self, project_id: str, participant_ids: List[str]) -> ChatRoom:
        # (保持不變)
        new_room = ChatRoom(
            room_id=str(uuid.uuid4()),
            context_project_id=project_id
        )
        self.db.add(new_room)
        participants = [
            ChatRoomParticipant(
                participant_id=str(uuid.uuid4()),
                room_id=new_room.room_id,
                user_id=uid
            )
            for uid in participant_ids
        ]
        self.db.add_all(participants)
        await self.db.flush()
        
        stmt = (
            select(ChatRoom)
            .where(ChatRoom.room_id == new_room.room_id)
            .options(
                selectinload(ChatRoom.participants) 
            )
        )
        result = await self.db.execute(stmt)
        loaded_new_room = result.scalars().first()

        if loaded_new_room is None:
            raise Exception("Failed to re-fetch newly created room")

        return loaded_new_room

    # --- Message 相關操作 (保持不變) ---

    async def get_messages_by_room_id(self, room_id: str, limit: int = 50, offset: int = 0) -> List[Message]:
        # (保持不變)
        stmt = (
            select(Message)
            .where(Message.room_id == room_id)
            .options(
                joinedload(Message.sender) 
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()[::-1]

    async def save_message(self, room_id: str, sender_id: str, content: str, content_type: str) -> Message:
        # (保持不變)
        new_message = Message(
            message_id=str(uuid.uuid4()),
            room_id=room_id,
            sender_id=sender_id,
            content=content,
            content_type=content_type
        )
        self.db.add(new_message)
        await self.db.flush()
        # (保持我們上次的修正)
        await self.db.refresh(new_message)
        
        return new_message

    async def mark_messages_as_read(self, room_id: str, user_id: str) -> None:
        # (保持不變)
        update_stmt = (
            update(Message)
            .where(
                and_(
                    Message.room_id == room_id,
                    Message.sender_id != user_id,
                    Message.is_read == False
                )
            )
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        await self.db.execute(update_stmt)