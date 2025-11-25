# app/services/profile_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, UploadFile, status
from typing import Union, List, Optional

from app.models.employer_profile import EmployerProfile
from app.models.freelancer_profile import FreelancerProfile
from app.models.user import User
from app.repositories.profile_repo import ProfileRepository
from app.repositories.review_repo import ReviewRepository
from app.schemas.profile_schema import (
    FreelancerProfileCreate, EmployerProfileCreate, UserSkillsUpdate,
    FreelancerProfileUpdate, EmployerProfileUpdate
)

from app.core.storage import get_storage_provider

class ProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProfileRepository(db)
        self.review_repo = ReviewRepository(db)

    async def get_my_profile(self, user: User):
        """依據角色取得自己的 Profile (含詳細評分)"""
        if user.role == "自由工作者":
            profile = await self.repo.get_freelancer_profile_by_user_id(user.user_id)
            if profile:
                ratings = await self.review_repo.get_freelancer_detailed_ratings(user.user_id)
                for key, value in ratings.items():
                    setattr(profile, key, value)
            return profile

        elif user.role == "雇主":
            profile = await self.repo.get_employer_profile_by_user_id(user.user_id)
            if profile:
                ratings = await self.review_repo.get_employer_detailed_ratings(user.user_id)
                for key, value in ratings.items():
                    setattr(profile, key, value)
            return profile

        return None 

    async def create_my_profile(self, user: User, profile_data: FreelancerProfileCreate | EmployerProfileCreate):
        """依據角色建立 Profile"""
        existing_profile = await self.get_my_profile(user)
        if existing_profile:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 已存在")

        if user.role == "自由工作者" and isinstance(profile_data, FreelancerProfileCreate):
            return await self.repo.create_freelancer_profile(user.user_id, profile_data)

        elif user.role == "雇主" and isinstance(profile_data, EmployerProfileCreate):
            return await self.repo.create_employer_profile(user.user_id, profile_data)

        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色與 Profile 類型不符")

    # --- (新增) 頭貼上傳邏輯 ---
    async def upload_avatar(self, file: UploadFile) -> str:
        """
        上傳頭貼或公司 Logo
        1. 驗證檔案類型 (僅限圖片)
        2. 呼叫 StorageProvider 儲存
        3. 回傳公開 URL
        """
        # 1. 驗證檔案類型
        allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="僅支援圖片格式 (JPEG, PNG, WEBP)"
            )

        # 2. 取得儲存實例 (Local 或 GCS 由設定檔決定)
        storage_provider = get_storage_provider()

        # 3. 執行儲存 (指定目錄為 'avatar')
        try:
            # 注意：這裡假設 save_file 會回傳完整的 URL (視 storage 實作而定)
            file_url = await storage_provider.save_file(file, directory="avatar")
            return file_url
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"圖片上傳失敗: {str(e)}"
            )
    
    async def update_my_skills(self, user: User, skills_data: UserSkillsUpdate):
        """(僅限工作者) 更新技能標籤"""
        if user.role != "自由工作者":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有自由工作者可以設定技能")

        profile = await self.repo.get_freelancer_profile_by_user_id(user.user_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "請先建立您的 Profile")

        return await self.repo.update_user_skills(profile.profile_id, skills_data.skill_tag_ids)

    async def update_my_profile(
        self, user: User, update_data: Union[FreelancerProfileUpdate, EmployerProfileUpdate]
    ):
        """
        業務邏輯：更新 Profile (基本資料/設定)
        """
        if user.role == "自由工作者":
            profile = await self.repo.get_freelancer_profile_by_user_id(user.user_id)
        elif user.role == "雇主":
            profile = await self.repo.get_employer_profile_by_user_id(user.user_id)
        else:
            profile = None

        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile 尚未建立")

        # 情況 1: 工作者
        if user.role == "自由工作者" and isinstance(update_data, FreelancerProfileUpdate):
            if not isinstance(profile, FreelancerProfile):
                 raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 類型不符")
            
            updated_profile = await self.repo.update_freelancer_profile(profile, update_data)
            
            ratings = await self.review_repo.get_freelancer_detailed_ratings(user.user_id)
            for key, value in ratings.items():
                setattr(updated_profile, key, value)
            return updated_profile

        # 情況 2: 雇主
        elif user.role == "雇主" and isinstance(update_data, EmployerProfileUpdate):
            if not isinstance(profile, EmployerProfile):
                 raise HTTPException(status.HTTP_400_BAD_REQUEST, "Profile 類型不符")
            
            updated_profile = await self.repo.update_employer_profile(profile, update_data)
            
            ratings = await self.review_repo.get_employer_detailed_ratings(user.user_id)
            for key, value in ratings.items():
                setattr(updated_profile, key, value)
            return updated_profile

        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色與 Profile 類型不符")

    async def get_freelancer_profile(self, user_id: str) -> FreelancerProfile:
        """
        獲取指定 ID 的工作者 Profile (公開用，含詳細評分)
        """
        profile = await self.repo.get_freelancer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "工作者 Profile 不存在")

        ratings = await self.review_repo.get_freelancer_detailed_ratings(user_id)
        for key, value in ratings.items():
            setattr(profile, key, value)

        return profile

    # (新增) 獲取雇主公開 Profile
    async def get_employer_profile_public(self, user_id: str) -> EmployerProfile:
        """
        獲取指定 ID 的雇主 Profile (公開用，含詳細評分)
        """
        # 1. 獲取基本資料
        profile = await self.repo.get_employer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "雇主 Profile 不存在")

        # 2. 計算並注入詳細評分
        ratings = await self.review_repo.get_employer_detailed_ratings(user_id)
        
        # 3. 將評分數據塞入 ORM 物件，供 Pydantic Schema 讀取
        for key, value in ratings.items():
            setattr(profile, key, value)

        return profile

    async def search_freelancers(
        self, tag_ids: Optional[List[str]] = None
    ) -> List[FreelancerProfile]:
        """
        搜尋公開的工作者 (含詳細評分)
        """
        profiles = await self.repo.list_public_freelancers_by_skills(tag_ids=tag_ids)
        
        for profile in profiles:
            ratings = await self.review_repo.get_freelancer_detailed_ratings(profile.user_id)
            for key, value in ratings.items():
                setattr(profile, key, value)
                
        return profiles