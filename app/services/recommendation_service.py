# app/services/recommendation_service.py (新檔案)
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Set
from sqlalchemy.future import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.models.freelancer_profile import FreelancerProfile
from app.models.user import User
from app.models.project import Project
from app.repositories.profile_repo import ProfileRepository
from app.repositories.project_repo import ProjectRepository
from app.utils.recommender import calculate_recommendation_scores

class RecommendationService:
    def __init__(self, db: AsyncSession):
        self.profile_repo = ProfileRepository(db)
        self.project_repo = ProjectRepository(db)
        self.db = db

    async def get_job_recommendations(self, user: User, limit: int = 10, offset: int = 0):

        """
        Use Case 5.1: 推薦案件給自由工作者
        """
        if user.role != "自由工作者":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有自由工作者可以接收案件推薦")

        # 1. 獲取工作者的技能
        profile = await self.profile_repo.get_freelancer_profile_by_user_id(user.user_id)
        if not profile or not profile.skills:
            return [] # 沒有 Profile 或沒有技能，無法推薦

        # 將技能轉換為名稱集合 (Set) 以利比對
        user_skill_names: Set[str] = {
            user_skill.tag.name.lower() for user_skill in profile.skills if user_skill.tag
        }
        
        # 2. 獲取所有活躍案件
        active_projects = await self.project_repo.list_active_projects_with_skills()
        
        # 3. 轉換案件資料結構
        projects_data_for_algo = []
        for project in active_projects:
            # ... (過濾 project.employer_id) ...
            
            project_skill_names: Set[str] = {
                proj_skill.tag.name.lower() for proj_skill in project.skills if proj_skill.tag
            }
            
            projects_data_for_algo.append({
                # (修正) 匹配 recommender.py 的新 key
                "item_id": project.project_id,
                "skill_names": project_skill_names,
                "item_object": project 
            })

        # 4. 呼叫演算法
        scored_projects = calculate_recommendation_scores(
            user_skill_names,
            projects_data_for_algo
        )

        total = len(scored_projects)
        # apply offset/limit (already sorted by algorithm)
        sliced = scored_projects[offset: offset + limit]

        # 5. 處理結果 - 提取物件和分數
        recommendations_with_scores = []
        for item in sliced:
            recommendations_with_scores.append({
                "project": item["item_object"],  # 原始 Project 物件
                "recommendation_score": round(item["score"], 2)  # 分數四捨五入到小數點後兩位
            })

        return {"items": recommendations_with_scores, "total": total}  # 回傳分頁結構

    
    async def get_freelancer_recommendations(self, user: User, limit: int = 10, offset: int = 0):
        """
        Use Case 5.2: 推薦工作者給雇主
        
        邏輯：
        1. 找出該雇主所有 '招募中' 案件。
        2. 彙總這些案件所需的所有 '不重複技能' (Set)。
        3. 找出所有 '公開' 的工作者 Profile。
        4. 使用推薦演算法，
           將 '雇主技能 Set' 與 '每個工作者的技能 Set' 進行匹配。
        """
        if user.role != "雇主":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有雇主可以接收人才推薦")

        # 1. & 2. 獲取雇主的所有 '招募中' 案件 並彙總所需技能
        # (注意：這裡我們不需要完整的 Project 物件，可以優化查詢)
        
        # (優化查詢：僅查詢雇主相關的招募中案件，並載入技能標籤)
        stmt = select(Project).where(
            Project.employer_id == user.user_id,
            Project.status == '招募中'
        )
        employer_projects = await self.db.execute(stmt)
        
        employer_skill_names: Set[str] = set()
        for project in employer_projects.scalars().all():
            for skill in project.skills:
                if skill.tag:
                    employer_skill_names.add(skill.tag.name.lower())
        
        if not employer_skill_names:
            return [] # 該雇主沒有招募中案件或案件沒設定技能，無法推薦

        # 3. 獲取所有公開的工作者
        public_freelancers = await self.profile_repo.list_public_freelancer_profiles_with_skills()

        # 4. 轉換資料結構
        freelancers_data_for_algo = []
        for profile in public_freelancers:
            # ... (過濾 profile.user_id) ...
            
            profile_skill_names: Set[str] = {
                user_skill.tag.name.lower() for user_skill in profile.skills if user_skill.tag
            }
            
            freelancers_data_for_algo.append({
                # (修正) 匹配 recommender.py 的新 key
                "item_id": profile.profile_id, 
                "skill_names": profile_skill_names,
                "item_object": profile 
            })

        # 5. 呼叫演算法
        scored_freelancers = calculate_recommendation_scores(
            employer_skill_names,
            freelancers_data_for_algo
        )

        logging.info(f"1 . Scored freelancers: {scored_freelancers}")

        total = len(scored_freelancers)
        sliced = scored_freelancers[offset: offset + limit]

        # 6. 處理結果 - 提取物件和分數
        recommendations_with_scores = []
        for item in sliced:
            recommendations_with_scores.append({
                "profile": item["item_object"],  # 原始 FreelancerProfile 物件
                "recommendation_score": round(item["score"], 2)  # 分數四捨五入到小數點後兩位
            })

        logging.info(f"2 . Scored freelancers: {scored_freelancers}")

        return {"items": recommendations_with_scores, "total": total}
