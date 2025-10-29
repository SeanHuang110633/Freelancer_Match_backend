# app/services/profile_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.models.employer_profile import EmployerProfile
from app.models.freelancer_profile import FreelancerProfile
from app.models.user import User
from app.repositories.profile_repo import ProfileRepository
from app.schemas.profile_schema import (
    FreelancerProfileCreate, EmployerProfileCreate, UserSkillsUpdate,FreelancerProfileUpdate, EmployerProfileUpdate
)
from typing import Union

class ProfileService:
    def __init__(self, db: AsyncSession):
        self.repo = ProfileRepository(db)
        self.db = db # Service 可能需要直接存取 db

    async def get_my_profile(self, user: User):
        """依據角色取得 Profile"""
        if user.role == "自由工作者":
            return await self.repo.get_freelancer_profile_by_user_id(user.user_id)
        elif user.role == "雇主":
            return await self.repo.get_employer_profile_by_user_id(user.user_id)
        return None # 管理員可能沒有 profile

    async def create_my_profile(self, user: User, profile_data: FreelancerProfileCreate | EmployerProfileCreate):
        """依據角色建立 Profile"""

        # 檢查是否已存在
        existing_profile = await self.get_my_profile(user)
        if existing_profile:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 已存在")

        if user.role == "自由工作者" and isinstance(profile_data, FreelancerProfileCreate):
            return await self.repo.create_freelancer_profile(user.user_id, profile_data)

        elif user.role == "雇主" and isinstance(profile_data, EmployerProfileCreate):
            return await self.repo.create_employer_profile(user.user_id, profile_data)

        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色與 Profile 類型不符")

    async def update_my_skills(self, user: User, skills_data: UserSkillsUpdate):
        """(僅限工作者) 更新技能標籤"""
        if user.role != "自由工作者":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有自由工作者可以設定技能")

        profile = await self.repo.get_freelancer_profile_by_user_id(user.user_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "請先建立您的 Profile")

        # (未來) 這裡可以加上驗證 tag_ids 是否都存在於 skill_tags 表

        return await self.repo.update_user_skills(profile.profile_id, skills_data.skill_tag_ids)
    
    async def update_my_profile(
        self, user: User, update_data: Union[FreelancerProfileUpdate, EmployerProfileUpdate]
    ):
        """
        業務邏輯：更新 Profile (基本資料/設定)
        """
        profile = await self.get_my_profile(user)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile 尚未建立")

        # 情況 1: 工作者
        if user.role == "自由工作者" and isinstance(update_data, FreelancerProfileUpdate):
            if not isinstance(profile, FreelancerProfile):
                 raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 類型不符")
            return await self.repo.update_freelancer_profile(profile, update_data)
        
        # 情況 2: 雇主
        elif user.role == "雇主" and isinstance(update_data, EmployerProfileUpdate):
            if not isinstance(profile, EmployerProfile):
                 raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 類型不符")
            return await self.repo.update_employer_profile(profile, update_data)
            
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色與 Profile 類型不符")
    
    async def get_freelancer_profile(self, user_id: str) -> FreelancerProfile:
        """獲取指定 ID 的工作者 Profile (公開用)"""
        profile = await self.repo.get_freelancer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "工作者 Profile 不存在")
            
        # (未來可加入 visibility 檢查)
        # if profile.visibility == '私人':
        #    raise HTTPException(status.HTTP_403_FORBIDDEN, "此 Profile 為私人")
            
        return profile