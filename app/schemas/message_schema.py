# app/schemas/message_schema.py

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

# 複用 UserOut
from app.schemas.user_schema import UserOut
from app.schemas.project_schema import ProjectOut

class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    joined_at: datetime
    # 這裡可以選擇性地包含 UserOut 物件，但為簡潔暫時只包含 ID

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message_id: str
    room_id: str
    sender_id: str
    content_type: str
    content: Optional[str] = None
    attachment_url: Optional[str] = None
    is_read: bool
    created_at: datetime
    # 為了顯示 Sender Name，可以巢狀 User
    sender: Optional[UserOut] = None 

class MessageIn(BaseModel):
    """
    用於 WebSocket 傳入的訊息格式 (text 或 JSON)
    """
    room_id: str
    content: str = Field(..., description="訊息內容")
    content_type: str = Field('text', description="'text' or 'file'")
    # 如果是文件，可以傳入 attachment_url

class RoomCreate(BaseModel):
    """
    用於建立新聊天室的請求體
    """
    # 至少需要一個上下文 ID 來關聯房間
    project_id: str = Field(..., description="關聯的案件 ID")
    # 可以選擇性地傳入受邀人的 ID (如果不是提案人)
    invited_user_id: Optional[str] = None

class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    room_id: str
    context_project_id: Optional[str]
    context_contract_id: Optional[str]
    created_at: datetime
    participants: List[ParticipantOut]
    # (注意: 不包含 messages，messages 通過單獨的 API 或 WS 獲取)
    # --- (必要修正) ---
    # 新增 project 欄位，Pydantic 會自動從 ORM 物件的 .project 屬性 讀取
    project: Optional[ProjectOut] = None
    # --- (修正結束) ---