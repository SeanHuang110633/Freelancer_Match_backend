# app/repositories/notification_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid, logging

from app.models.notification import Notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(self, notification: Notification) -> Notification:
        """
        新增一筆通知
        """
        # --- (必要修正) ---
        try:
            # --- (必要修正) ---
            # 修正 Commit 和 Refresh 的順序
            # 步驟 1: 加入 Session
            self.db.add(notification)
            # 步驟 2: 執行 INSERT (Flush)
            await self.db.flush() 
            # 步驟 3: 獲取 DB 產生的預設值 (例如 created_at) (Refresh)
            await self.db.refresh(notification)
            # 步驟 4: 提交事務 (Commit)
            await self.db.commit() 
            return notification
            # --- (修正結束) ---
        
        except Exception as e:
            await self.db.rollback() 
            logger.error(f"建立通知失敗: {e}", exc_info=True)
            raise
        

    async def get_notification_by_id(self, notification_id: str) -> Optional[Notification]:
        """
        依 ID 獲取通知 (主要用於權限檢查)
        """
        stmt = select(Notification).where(Notification.notification_id == notification_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_notifications_by_user(self, user_id: str, limit: int = 20) -> List[Notification]:
        """
        獲取某位使用者的所有通知 (依時間降序排列)
        """
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def mark_as_read(self, notification: Notification) -> Notification:
        """
        將單一通知設為已讀
        """
        logging.info(f"標記已讀到repo了: {notification.notification_id}")
        notification.is_read = True
        # 步驟 1: 刷新 Session，確保 UPDATE 語句被發送到資料庫
        await self.db.flush() 
    
        # 【關鍵修正】步驟 2: 提交事務，將變更寫入資料庫
        await self.db.commit() 
        
        # 步驟 3: 刷新物件以獲取最新的狀態 (雖然這裡沒必要，但可保持一致性)
        await self.db.refresh(notification)
        return notification

    # (可選)
    # async def mark_all_as_read(self, user_id: str): ...