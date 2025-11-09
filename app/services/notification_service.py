# app/services/notification_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Optional

from app.models.user import User
from app.models.notification import Notification
from app.repositories.notification_repo import NotificationRepository

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    async def create_notification(
        self,
        user_id: str,
        title: str,
        link_url: str,
        message: Optional[str] = None
    ) -> Notification:
        """
        (內部使用) 供其他 Service 呼叫的介面
        """
        new_notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            link_url=link_url,
            is_read=False
        )
        logging.info(f"建立通知 for User ID: {user_id}, Title: {title}, Link: {link_url}, Message: {message}")
        return await self.repo.create_notification(new_notification)

    async def get_my_notifications(self, user: User) -> List[Notification]:
        """
        (API 用) 獲取當前登入者的通知列表
        """
        return await self.repo.list_notifications_by_user(user.user_id)

    async def mark_notification_as_read(
        self, 
        notification_id: str, 
        user: User
    ) -> Notification:
        """
        (API 用) 將通知設為已讀，並檢查權限
        """
        notification = await self.repo.get_notification_by_id(notification_id)
        
        if not notification:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "通知不存在")
        
        # (重要) 只能標記自己的通知
        if notification.user_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "無權操作此通知")
            
        if notification.is_read:
            return notification # 已讀，直接回傳
            
        return await self.repo.mark_as_read(notification)