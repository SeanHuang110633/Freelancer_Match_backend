# app/routers/notification_router.py

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.services.notification_service import NotificationService
from app.schemas.notification_schema import NotificationOut

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)

@router.get(
    "/my", 
    response_model=List[NotificationOut],
    summary="獲取我的通知列表"
)
async def get_my_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.3) 獲取當前登入者的通知列表 (依時間倒序)。
    前端應使用此 API 定期輪詢 (Polling)。
    """
    service = NotificationService(db)
    return await service.get_my_notifications(current_user)

@router.patch(
    "/{notification_id}/read", 
    response_model=NotificationOut,
    summary="將通知設為已讀"
)
async def mark_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (M8.3) 當使用者點擊通知時，前端應呼叫此 API 將其標記為已讀。
    """
    service = NotificationService(db)
    return await service.mark_notification_as_read(notification_id, current_user)