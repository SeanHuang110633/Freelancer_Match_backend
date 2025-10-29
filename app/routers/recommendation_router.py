# app/routers/recommendation_router.py (新檔案)
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.recommendation_service import RecommendationService
from app.schemas.project_schema import ProjectRecommendationOut
from app.schemas.profile_schema import FreelancerRecommendationOut
router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/jobs", response_model=List[ProjectRecommendationOut])
async def get_recommended_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    獲取推薦給當前 (自由工作者) 的案件列表
   
    """
    service = RecommendationService(db)
    projects = await service.get_job_recommendations(current_user)
    return projects

@router.get("/freelancers", response_model=List[FreelancerRecommendationOut])
async def get_recommended_freelancers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    獲取推薦給當前 (雇主) 的工作者列表
   
    """
    service = RecommendationService(db)
    freelancers = await service.get_freelancer_recommendations(current_user)
    return freelancers