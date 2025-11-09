# app/models/notification.py

import uuid
from sqlalchemy import Column, String, TEXT, BOOLEAN, CHAR, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # (重要) 關聯到接收通知的 user
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    message = Column(TEXT)
    
    # (關鍵) 點擊通知後要導向的前端 URL
    link_url = Column(String(500)) 
    
    is_read = Column(BOOLEAN, default=False, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # 建立反向關聯
    user = relationship("User")