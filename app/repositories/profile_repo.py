# app/repositories/profile_repo.py
import json
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy import func # (新增)

# (新增) 匯入快取與 Redis
from app.core.redis import redis_manager
from app.core.cache import cached
from pydantic import TypeAdapter

# (新增) 匯入 Schema 用於序列化
from app.schemas.profile_schema import FreelancerProfileCreate, EmployerProfileCreate
from app.schemas.profile_schema import FreelancerProfileUpdate, EmployerProfileUpdate
from app.schemas.profile_schema import FreelancerProfileOut, EmployerProfileOut

from app.models.freelancer_profile import FreelancerProfile
from app.models.employer_profile import EmployerProfile
from app.models.skill_tag import UserSkillTag, SkillTag


class ProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Freelancer ---
    
    # (保持不變)
    async def get_freelancer_profile_by_user_id(self, user_id: str) -> FreelancerProfile | None:
        stmt = select(FreelancerProfile).where(FreelancerProfile.user_id == user_id)
        stmt = stmt.options(
            selectinload(FreelancerProfile.skills).selectinload(UserSkillTag.tag)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # (保持不變)
    async def get_freelancer_profile_view(self, user_id: str) -> Optional[FreelancerProfileOut]:
        cache_key = f"profile:freelancer:view:{user_id}"
        cached_data = await redis_manager.get_value(cache_key)
        if cached_data:
            try:
                return FreelancerProfileOut.model_validate_json(cached_data)
            except Exception:
                pass 

        profile = await self.get_freelancer_profile_by_user_id(user_id)
        if not profile:
            return None

        profile_out = FreelancerProfileOut.model_validate(profile)
        try:
            data_dict = jsonable_encoder(profile_out)
            await redis_manager.set_value(cache_key, json.dumps(data_dict), expire=3600)
        except Exception as e:
            pass

        return profile_out

    # (保持不變)
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
    
    # (保持不變)
    async def update_freelancer_profile(
        self, profile: FreelancerProfile, update_data: FreelancerProfileUpdate
    ) -> FreelancerProfile:
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(profile, key, value)
            
        await self.db.commit()
        await self.db.refresh(profile)

        await redis_manager.delete_key(f"profile:freelancer:view:{profile.user_id}")
        await redis_manager.delete_keys_by_pattern("profile:search:*")

        return profile

    
    # --- Employer ---
    
    # (保持不變)
    async def get_employer_profile_by_user_id(self, user_id: str) -> EmployerProfile | None:
        stmt = select(EmployerProfile).where(EmployerProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # (保持不變)
    async def get_employer_profile_view(self, user_id: str) -> Optional[EmployerProfileOut]:
        cache_key = f"profile:employer:view:{user_id}"
        cached_data = await redis_manager.get_value(cache_key)
        if cached_data:
            try:
                return EmployerProfileOut.model_validate_json(cached_data)
            except Exception:
                pass

        profile = await self.get_employer_profile_by_user_id(user_id)
        if not profile:
            return None

        profile_out = EmployerProfileOut.model_validate(profile)
        try:
            data_dict = jsonable_encoder(profile_out)
            await redis_manager.set_value(cache_key, json.dumps(data_dict), expire=3600)
        except Exception:
            pass

        return profile_out

    # (保持不變)
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

    # (保持不變)
    async def update_employer_profile(
        self, profile: EmployerProfile, update_data: EmployerProfileUpdate
    ) -> EmployerProfile:
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(profile, key, value)
            
        await self.db.commit()
        await self.db.refresh(profile)
        await redis_manager.delete_key(f"profile:employer:view:{profile.user_id}")
        return profile

    # (保持不變)
    async def update_user_skills(self, profile_id: str, tag_ids: List[str]) -> List[UserSkillTag]:
        profile = await self.db.get(FreelancerProfile, profile_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

        stmt = select(FreelancerProfile).where(FreelancerProfile.profile_id == profile_id).options(selectinload(FreelancerProfile.skills))
        result = await self.db.execute(stmt)
        loaded_profile = result.scalars().first()

        loaded_profile.skills.clear()
        await self.db.flush()

        for tag_id in tag_ids:
            new_link = UserSkillTag(
                user_skill_tag_id=str(uuid.uuid4()),
                profile_id=profile_id,
                tag_id=tag_id
            )
            loaded_profile.skills.append(new_link)

        await self.db.commit()

        await redis_manager.delete_key(f"profile:freelancer:view:{loaded_profile.user_id}")
        await redis_manager.delete_keys_by_pattern("profile:search:*")

        final_stmt = select(FreelancerProfile).where(FreelancerProfile.user_id == loaded_profile.user_id).options(
            selectinload(FreelancerProfile.skills).selectinload(UserSkillTag.tag)
        ).execution_options(populate_existing=True) 
        
        final_result = await self.db.execute(final_stmt)
        final_profile = final_result.scalars().first()

        if final_profile is None:
             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to re-fetch profile")

        return final_profile.skills
    
    # (保持不變)
    async def list_public_freelancer_profiles_with_skills(self) -> List[FreelancerProfile]:
        stmt = select(FreelancerProfile).where(FreelancerProfile.visibility == '公開')
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # (修改) 支援分頁的搜尋 (移除快取，改為只查分頁)
    async def list_public_freelancers_by_skills(
        self, 
        tag_ids: Optional[List[str]] = None,
        limit: int = 20, 
        offset: int = 0
    ) -> List[FreelancerProfile]:
        """
        支援分頁的搜尋
        """
        stmt = select(FreelancerProfile).options(
            selectinload(FreelancerProfile.skills).joinedload(UserSkillTag.tag) 
        )
        
        stmt = stmt.where(FreelancerProfile.visibility == '公開')

        if tag_ids:
            stmt = stmt.join(
                UserSkillTag, FreelancerProfile.profile_id == UserSkillTag.profile_id
            ).where(UserSkillTag.tag_id.in_(tag_ids))

        # 加入分頁
        stmt = stmt.distinct().limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # (新增) 計算總筆數 (給前端分頁器用)
    async def count_public_freelancers_by_skills(
        self, tag_ids: Optional[List[str]] = None
    ) -> int:
        # 使用 func.count(DISTINCT ...) 確保多對多關聯計算正確
        stmt = select(func.count(func.distinct(FreelancerProfile.profile_id))).where(FreelancerProfile.visibility == '公開')
        
        if tag_ids:
            stmt = stmt.join(
                UserSkillTag, FreelancerProfile.profile_id == UserSkillTag.profile_id
            ).where(UserSkillTag.tag_id.in_(tag_ids))
            
        result = await self.db.execute(stmt)
        return result.scalar() or 0