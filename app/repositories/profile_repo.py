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
    async def update_user_skills(self, profile_id: str, tag_ids: List[str]) -> List[UserSkillTag]:
        
        # 1. 獲取 Profile (這裡不需要 eager load skills，因為我們馬上要清空它)
        profile = await self.db.get(FreelancerProfile, profile_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
            
        # 2. 為了清空舊技能，我們需要先確保 skills 集合被載入
        # 使用 selectinload 確保 skills 在記憶體中
        # (雖然這看起來有點多餘，但為了安全操作集合是必要的)
        stmt = select(FreelancerProfile).where(FreelancerProfile.profile_id == profile_id).options(selectinload(FreelancerProfile.skills))
        result = await self.db.execute(stmt)
        loaded_profile = result.scalars().first()
        
        # 清空舊關聯
        loaded_profile.skills.clear()
        
        # 3. 建立新關聯
        for tag_id in tag_ids:
            new_link = UserSkillTag(
                user_skill_tag_id=str(uuid.uuid4()),
                profile_id=profile_id,
                tag_id=tag_id
            )
            # 直接加到 skills 集合中，讓 ORM 幫我們處理 INSERT
            loaded_profile.skills.append(new_link)
            
        # 4. 提交
        await self.db.commit()
        
        # 5. (關鍵修正) 為了回傳正確資料，我們不再依賴 expire/refresh
        # 而是"手動"重新查詢一次完整的物件
        # 使用一個全新的查詢，確保拿到的是 DB 最新狀態
        # 這裡我們直接呼叫既有的 get_freelancer_profile_by_user_id 方法
        # 它內部有正確的 selectinload 邏輯
        
        # 注意：我們需要確保這個查詢不會用到 Session 裡的舊快取
        # 雖然我們沒用 expire，但因為我們是在同一個 transaction 裡做了修改
        # 透過直接查詢，通常能拿到最新狀態。
        # 為了保險，我們可以使用 populate_existing() 強制覆蓋
        
        final_stmt = select(FreelancerProfile).where(FreelancerProfile.user_id == loaded_profile.user_id).options(
            selectinload(FreelancerProfile.skills).selectinload(UserSkillTag.tag)
        ).execution_options(populate_existing=True) # <--- 強制更新 Session 中的物件
        
        final_result = await self.db.execute(final_stmt)
        final_profile = final_result.scalars().first()

        if final_profile is None:
             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to re-fetch profile")

        return final_profile.skills
    
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