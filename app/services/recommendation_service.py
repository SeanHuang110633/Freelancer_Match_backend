# app/services/recommendation_service.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Set, Dict 
from sqlalchemy.future import select
# (修正) 新增這行匯入
from sqlalchemy.orm import selectinload, joinedload

from app.core.cache import cached
from pydantic import TypeAdapter
from app.schemas.project_schema import PaginatedProjectRecommendationOut
from app.schemas.profile_schema import PaginatedFreelancerRecommendationOut

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.models.freelancer_profile import FreelancerProfile
from app.models.user import User
from app.models.project import Project, ProjectSkillTag # (修正) 確保 ProjectSkillTag 也有匯入
from app.repositories.profile_repo import ProfileRepository
from app.repositories.project_repo import ProjectRepository
from app.utils.recommender import calculate_recommendation_scores

class RecommendationService:
    def __init__(self, db: AsyncSession):
        self.profile_repo = ProfileRepository(db)
        self.project_repo = ProjectRepository(db)
        self.db = db

    # ... (get_job_recommendations 保持不變) ...
    @cached(key_prefix="rec:jobs", expire=600, model=PaginatedProjectRecommendationOut)
    async def get_job_recommendations(
        self, user: User, limit: int = 10, offset: int = 0
    ) -> Dict:
        if user.role != "自由工作者":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有自由工作者可以接收案件推薦")

        profile = await self.profile_repo.get_freelancer_profile_by_user_id(user.user_id)
        if not profile or not profile.skills:
            return {"items": [], "total": 0}

        user_skill_names: Set[str] = {
            user_skill.tag.name.lower() for user_skill in profile.skills if user_skill.tag
        }
        
        active_projects = await self.project_repo.list_active_projects_with_skills()
        
        projects_data_for_algo = []
        for project in active_projects:
            if project.employer_id == user.user_id:
                continue

            project_skill_names: Set[str] = {
                proj_skill.tag.name.lower() for proj_skill in project.skills if proj_skill.tag
            }
            
            projects_data_for_algo.append({
                "item_id": project.project_id,
                "skill_names": project_skill_names,
                "item_object": project 
            })

        scored_projects = calculate_recommendation_scores(
            user_skill_names,
            projects_data_for_algo
        )

        total = len(scored_projects)
        sliced = scored_projects[offset: offset + limit]

        recommendations_with_scores = []
        for item in sliced:
            recommendations_with_scores.append({
                "project": item["item_object"],
                "recommendation_score": round(item["score"], 2)
            })

        return {"items": recommendations_with_scores, "total": total}

    
    # ... (get_freelancer_recommendations) ...
    @cached(key_prefix="rec:freelancers", expire=600, model=PaginatedFreelancerRecommendationOut)
    async def get_freelancer_recommendations(
        self, user: User, limit: int = 10, offset: int = 0
    ) -> Dict:
        if user.role != "雇主":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有雇主可以接收人才推薦")

        # 1. & 2. 獲取雇主的所有 '招募中' 案件 並彙總所需技能
        stmt = select(Project).where(
            Project.employer_id == user.user_id,
            Project.status == '招募中'
        ).options(
            # (修正) 這行之前報錯是因為 selectinload 未定義
            selectinload(Project.skills).joinedload(ProjectSkillTag.tag) 
        )
        employer_projects = await self.db.execute(stmt)
        
        employer_skill_names: Set[str] = set()
        for project in employer_projects.scalars().all():
            for skill in project.skills:
                if skill.tag:
                    employer_skill_names.add(skill.tag.name.lower())
        
        if not employer_skill_names:
            return {"items": [], "total": 0} 

        # 3. 獲取所有公開的工作者
        public_freelancers = await self.profile_repo.list_public_freelancer_profiles_with_skills()

        # 4. 轉換資料結構
        freelancers_data_for_algo = []
        for profile in public_freelancers:
            if profile.user_id == user.user_id:
                continue
            
            profile_skill_names: Set[str] = {
                user_skill.tag.name.lower() for user_skill in profile.skills if user_skill.tag
            }
            
            freelancers_data_for_algo.append({
                "item_id": profile.profile_id, 
                "skill_names": profile_skill_names,
                "item_object": profile 
            })

        # 5. 呼叫演算法
        scored_freelancers = calculate_recommendation_scores(
            employer_skill_names,
            freelancers_data_for_algo
        )

        logging.info(f"1 . Scored freelancers count: {len(scored_freelancers)}")

        total = len(scored_freelancers)
        sliced = scored_freelancers[offset: offset + limit]

        # 6. 處理結果
        recommendations_with_scores = []
        for item in sliced:
            recommendations_with_scores.append({
                "profile": item["item_object"], 
                "recommendation_score": round(item["score"], 2)
            })

        return {"items": recommendations_with_scores, "total": total}