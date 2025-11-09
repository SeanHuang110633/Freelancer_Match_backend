# app/schemas/notification_schema.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class NotificationOut(BaseModel):
    """
    用於 API 回傳的通知格式
    """
    model_config = ConfigDict(from_attributes=True)

    notification_id: str
    user_id: str
    title: str
    message: Optional[str] = None
    link_url: Optional[str] = None
    is_read: bool
    created_at: datetime