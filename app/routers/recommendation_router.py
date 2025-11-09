# app/routers/recommendation_router.py (新檔案)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.recommendation_service import RecommendationService
from app.schemas.project_schema import PaginatedProjectRecommendationOut
from app.schemas.profile_schema import PaginatedFreelancerRecommendationOut
router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/jobs", response_model=PaginatedProjectRecommendationOut)
async def get_recommended_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
):
    """
    獲取推薦給當前 (自由工作者) 的案件列表
   
    """
    # enforce server-side cap
    max_limit = 100
    limit = min(limit, max_limit)

    service = RecommendationService(db)
    result = await service.get_job_recommendations(current_user, limit=limit, offset=offset)
    return result

@router.get("/freelancers", response_model=PaginatedFreelancerRecommendationOut)
async def get_recommended_freelancers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
):
    """
    獲取推薦給當前 (雇主) 的工作者列表
   
    """
    max_limit = 100
    limit = min(limit, max_limit)

    service = RecommendationService(db)
    result = await service.get_freelancer_recommendations(current_user, limit=limit, offset=offset)
    return result