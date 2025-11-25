# app/routers/review_router.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.review_schema import ReviewCreate, ReviewOut
from app.services.review_service import ReviewService

router = APIRouter(
    prefix="/reviews",
    tags=["Reviews & Reputation"],
    dependencies=[Depends(get_current_user)]
)

def get_review_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(db)

@router.post(
    "/",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="M9.1 提交評價"
)
async def create_review(
    review_data: ReviewCreate,
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雙方) 在合約完成後提交評價。
    - 雇主評工作者：需填寫 _fw 結尾的欄位。
    - 工作者評雇主：需填寫 _we 結尾的欄位。
    - 每個合約一人只能評價一次，且不可修改。
    """
    return await service.create_review(review_data, current_user)

@router.get(
    "/contract/{contract_id}",
    response_model=List[ReviewOut],
    summary="M9.2 獲取合約的評價"
)
async def get_contract_reviews(
    contract_id: str,
    service: ReviewService = Depends(get_review_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雙方) 查看該合約的評價內容 (最多兩筆)。
    """
    return await service.get_reviews_for_contract(contract_id, current_user)