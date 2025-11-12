# app/repositories/profile_repo.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from app.models.freelancer_profile import FreelancerProfile
from app.models.employer_profile import EmployerProfile
from app.models.skill_tag import UserSkillTag, SkillTag
from app.schemas.profile_schema import FreelancerProfileCreate, EmployerProfileCreate
from app.schemas.profile_schema import FreelancerProfileUpdate, EmployerProfileUpdate
from typing import List, Optional
import uuid
from fastapi import HTTPException, status


class ProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Freelancer ---
    # (重要)
    # 我們需要確保 get_freelancer_profile_by_user_id
    # 確實 Eager Load 了所有需要的關聯
    async def get_freelancer_profile_by_user_id(self, user_id: str) -> FreelancerProfile | None:
        stmt = select(FreelancerProfile).where(FreelancerProfile.user_id == user_id)
        
        # (修正) 明確指定 Eager Loading 
        # 雖然 lazy="selectin" 應該會處理，但明確指定更安全
        stmt = stmt.options(
            selectinload(FreelancerProfile.skills).selectinload(UserSkillTag.tag)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_freelancer_profile(self, user_id: str, profile_data: FreelancerProfileCreate) -> FreelancerProfile:
        new_profile = FreelancerProfile(
            **profile_data.model_dump(),
            profile_id=str(uuid.uuid4()),
            user_id=user_id
        )
        self.db.add(new_profile)
        await self.db.commit()
        await self.db.refresh(new_profile)
        return new_profile
    
    async def update_freelancer_profile(
        self, profile: FreelancerProfile, update_data: FreelancerProfileUpdate
    ) -> FreelancerProfile:
        """更新工作者 Profile"""
        
        # 使用 Pydantic 的 .model_dump() 搭配 exclude_unset=True
        # 這會產生一個只包含 "有被傳入" 欄位的 dict
        update_dict = update_data.model_dump(exclude_unset=True)
        
        for key, value in update_dict.items():
            setattr(profile, key, value)
            
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    
    

    # --- Employer ---
    async def get_employer_profile_by_user_id(self, user_id: str) -> EmployerProfile | None:
        stmt = select(EmployerProfile).where(EmployerProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_employer_profile(self, user_id: str, profile_data: EmployerProfileCreate) -> EmployerProfile:
        new_profile = EmployerProfile(
            **profile_data.model_dump(),
            profile_id=str(uuid.uuid4()),
            user_id=user_id
        )
        self.db.add(new_profile)
        await self.db.commit()
        await self.db.refresh(new_profile)
        return new_profile

    async def update_employer_profile(
        self, profile: EmployerProfile, update_data: EmployerProfileUpdate
    ) -> EmployerProfile:
        """更新雇主 Profile"""
        update_dict = update_data.model_dump(exclude_unset=True)
        
        for key, value in update_dict.items():
            setattr(profile, key, value)
            
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    # (重要) 修正 update_user_skills
    async def update_user_skills(self, profile_id: str, tag_ids: List[str]) -> List[UserSkillTag]: # <-- (Fix 1) 修正回傳型別提示
        
        profile = await self.db.get(
            FreelancerProfile, 
            profile_id, 
            options=[selectinload(FreelancerProfile.skills)]
        )
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
            
        profile.skills.clear()
        
        await self.db.flush() # 確保 DELETE 執行

        new_skill_links = []
        for tag_id in tag_ids:
            new_link = UserSkillTag(
                user_skill_tag_id=str(uuid.uuid4()),
                profile_id=profile_id,
                tag_id=tag_id
            )
            new_skill_links.append(new_link)
            
        self.db.add_all(new_skill_links)
        
        await self.db.commit() # 確保 INSERT 執行
        
        # 重新獲取完整的 Profile 物件
        updated_profile = await self.get_freelancer_profile_by_user_id(profile.user_id)
        
        if updated_profile is None:
             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to re-fetch profile")

        return updated_profile.skills # <-- (Fix 2) 回傳技能列表，而不是 Profile 物件
    
    async def list_public_freelancer_profiles_with_skills(self) -> List[FreelancerProfile]:
        """
        獲取所有 '公開' 的工作者 Profile，並預先載入技能
        """
        # (重要)
        # 由於 Model 已設定 lazy="selectin"，
        # 我們只需查詢 FreelancerProfile 並過濾 visibility，
        # SQLAlchemy 會自動處理 'skills' 和 'skills.tag' 的 Eager Loading
        stmt = select(FreelancerProfile).where(FreelancerProfile.visibility == '公開')
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # (新增) 需求：雇主搜尋工作者
    async def list_public_freelancers_by_skills(
        self, tag_ids: Optional[List[str]] = None
    ) -> List[FreelancerProfile]:
        """
        (核心功能) 依技能標籤搜尋「公開」的工作者
        1. 僅限 '公開'
        2. 技能 (tag_ids): 任一標籤符合 (OR 邏輯)
        """
        
        # 基礎查詢 (SELECT * FROM freelancer_profiles)
        # 必須 Eager Load 'skills' 及其 'tag' 以滿足 FreelancerProfileOut Schema
        stmt = select(FreelancerProfile).options(
            selectinload(FreelancerProfile.skills)
            .joinedload(UserSkillTag.tag) # 使用 joinedload 避免 N+1
        )
        
        # 1. 篩選 visibility
        stmt = stmt.where(FreelancerProfile.visibility == '公開')

        # 2. 處理技能標籤 (tag_ids)
        if tag_ids:
            # 我們需要 JOIN 關聯表 UserSkillTag
            # 並篩選 tag_id 在我們傳入的列表中
            stmt = stmt.join(
                UserSkillTag, FreelancerProfile.profile_id == UserSkillTag.profile_id
            ).where(
                UserSkillTag.tag_id.in_(tag_ids)
            )

        # (重要) 使用 distinct() 確保如果一個工作者符合多個標籤，
        # 他在列表中只出現一次。
        result = await self.db.execute(stmt.distinct())
        return result.scalars().all()