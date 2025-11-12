# app/routers/profile_router.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.profile_service import ProfileService
from app.schemas.profile_schema import (
    FreelancerProfileCreate, EmployerProfileCreate,
    FreelancerProfileOut, EmployerProfileOut,
    UserSkillsUpdate, UserSkillTagOut,FreelancerProfileUpdate, EmployerProfileUpdate
)
from typing import Union, List

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(
    prefix="/profiles",
    tags=["Profiles"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/me", response_model=Union[FreelancerProfileOut, EmployerProfileOut, None])
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    獲取當前登入者的 Profile。
    如果尚未建立，將回傳 200 OK (body 為 null)。
    """
    service = ProfileService(db)
    profile = await service.get_my_profile(current_user)
    return profile # 回傳 Model 或 None

@router.post("/me", response_model=Union[FreelancerProfileOut, EmployerProfileOut])
async def create_my_profile(
    # (重要) 根據 Pydantic 的 Union，FastAPI 會自動嘗試解析
    profile_data: Union[FreelancerProfileCreate, EmployerProfileCreate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    建立當前登入者的 Profile (工作者 / 雇主)
    """
    service = ProfileService(db)
    # Service 層會處理角色驗證
    new_profile = await service.create_my_profile(current_user, profile_data)

    # 建立後，重新查詢一次以獲取完整的(含 Eager Loading)資料
    profile = await service.get_my_profile(current_user)
    return profile

# (新增) PUT /profiles/me
@router.put("/me", response_model=Union[FreelancerProfileOut, EmployerProfileOut])
async def update_my_profile(
    update_data: Union[FreelancerProfileUpdate, EmployerProfileUpdate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新當前登入者的 Profile (基本資料 / 設定)
    """
    service = ProfileService(db)
    updated_profile = await service.update_my_profile(current_user, update_data)
    
    # (重要) 
    # 為了確保 Eager Loading 正確執行，我們重新 get 一次
    # (我們在 Repo 的 get_... 方法中定義了 selectinload)
    profile = await service.get_my_profile(current_user)
    return profile

# (新增) PUT /profiles/freelancer/skills
@router.put("/freelancer/skills", response_model=List[UserSkillTagOut])
async def update_freelancer_skills(
    skills_data: UserSkillsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (僅限工作者) 更新技能標籤。
    傳入 tag_id 列表，伺服器會覆蓋現有技能。
    """
    service = ProfileService(db)
    updated_skills = await service.update_my_skills(current_user, skills_data)
    return updated_skills

# (新增) 獲取公開工作者 Profile
@router.get("/freelancer/{user_id}", response_model=FreelancerProfileOut)
async def get_public_freelancer_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db)
    # (注意) 這個 API 不需要 get_current_user，因為是公開查看
    # 但我們先保留 router 的全局依賴，稍後可調整
):
    """
    獲取指定 User ID 的工作者公開 Profile
    """
    service = ProfileService(db)
    profile = await service.get_freelancer_profile(user_id)
    return profile


# (新增) 需求：雇主搜尋工作者
@router.get(
    "/freelancers/search", 
    response_model=List[FreelancerProfileOut],
    summary="搜尋公開的工作者"
)
async def search_public_freelancers(
    request: Request, # 注入 Request 以處理陣列參數
    db: AsyncSession = Depends(get_db)
):
    """
    (雇主) 依技能標籤搜尋「公開」的工作者 Profile。
    
    前端應使用 `tag_id[]` 作為 query 參數名稱來傳遞陣列。
    """
    # 仿照 project_router.py，從 query_params 手動解析陣列
    logger.info("Request query parameters: %s", request.query_params)
    # 支援兩種前端傳陣列的參數名稱：`tag_id` (tag_id=...&tag_id=...) 或 `tag_id[]` (tag_id[]=...)
    tag_ids_from_query = request.query_params.getlist("tag_id")
    if not tag_ids_from_query:
        tag_ids_from_query = request.query_params.getlist("tag_id[]")
    logger.info("Received tag_ids from query: %s", tag_ids_from_query)

    # 如果列表為空，則設為 None
    tag_ids = tag_ids_from_query if tag_ids_from_query else None
    
    service = ProfileService(db)
    profiles = await service.search_freelancers(tag_ids=tag_ids)
    
    return profiles