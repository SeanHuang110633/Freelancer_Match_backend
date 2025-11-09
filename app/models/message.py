# app/models/message.py

import uuid
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, CHAR, func, Boolean
# (新增) 匯入 Column 以便在 foreign_keys 中引用
from sqlalchemy.orm import relationship
from app.core.database import Base

class ChatRoom(Base):
    __tablename__ = "chat_rooms"
    room_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # --- 修正：定義外鍵欄位 ---
    context_project_id = Column(CHAR(36), ForeignKey("projects.project_id", ondelete="SET NULL"), nullable=True, index=True)
    context_contract_id = Column(CHAR(36), ForeignKey("contracts.contract_id", ondelete="SET NULL"), nullable=True, index=True)
    # --- 修正結束 ---
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # --- 必要修正：明確指定 foreign_keys ---
    project = relationship(
        "Project", 
        back_populates="chat_rooms",
        foreign_keys="[ChatRoom.context_project_id]" # 告訴 SQLAlchemy 使用這個欄位
    )
    contract = relationship(
        "Contract", 
        # back_populates="chat_rooms",
        foreign_keys="[ChatRoom.context_contract_id]" # 告訴 SQLAlchemy 使用這個欄位
    )
    # --- 修正結束 ---
    
    # (保持我們上次的修正)
    participants = relationship(
        "ChatRoomParticipant",
        back_populates="room",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    messages = relationship(
        "Message",
        back_populates="room",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

class ChatRoomParticipant(Base):
    __tablename__ = "chat_room_participants"
    participant_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(CHAR(36), ForeignKey("chat_rooms.room_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(TIMESTAMP, server_default=func.now())
    
    room = relationship("ChatRoom", back_populates="participants")
    # (保持我們上次的修正)
    user = relationship("User", lazy="selectin") 

class Message(Base):
    __tablename__ = "messages"
    message_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(CHAR(36), ForeignKey("chat_rooms.room_id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    content_type = Column(String(50), default='text')
    content = Column(Text)
    attachment_url = Column(String(500))
    is_read = Column(Boolean, default=False) 
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    room = relationship("ChatRoom", back_populates="messages")
    
    # (保持我們上次的修正)
    sender = relationship("User", lazy="selectin")