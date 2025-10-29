# app/routers/user_router.py
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user_schema import UserOut

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)] # (重要) 整個路由都需要登入
)

@router.get("/me", response_model=UserOut)
async def read_users_me(
    current_user: User = Depends(get_current_user)
):
    """
    獲取當前登入使用者的基本資料 (不含密碼)
    """
    return current_user