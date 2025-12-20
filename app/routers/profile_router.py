# app/routers/profile_router.py
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.profile_service import ProfileService
from app.schemas.profile_schema import (
    FreelancerProfileCreate, EmployerProfileCreate,
    FreelancerProfileOut, EmployerProfileOut,
    UserSkillsUpdate, UserSkillTagOut, FreelancerProfileUpdate, EmployerProfileUpdate,
    PaginatedFreelancerSearchOut # (新增)
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
    return profile

@router.post("/me", response_model=Union[FreelancerProfileOut, EmployerProfileOut])
async def create_my_profile(
    profile_data: Union[FreelancerProfileCreate, EmployerProfileCreate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    建立當前登入者的 Profile (工作者 / 雇主)
    """
    service = ProfileService(db)
    new_profile = await service.create_my_profile(current_user, profile_data)
    profile = await service.get_my_profile(current_user)
    return profile

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
    profile = await service.get_my_profile(current_user)
    return profile

# --- 上傳頭貼的 Endpoint ---
@router.post(
    "/avatar",
    response_model=dict,
    summary="上傳頭貼/Logo",
    description="上傳圖片並取得 URL，供後續建立或更新 Profile 使用。"
)
async def upload_avatar_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    # 雖然上傳本身不依賴 user 資料，但我們保留 user 檢查確保已登入
    current_user: User = Depends(get_current_user) 
):
    """
    Input: multipart/form-data (file)
    Output: { "url": "http://..." }
    """
    service = ProfileService(db)
    url = await service.upload_avatar(file)
    return {"url": url}


@router.put("/freelancer/skills", response_model=List[UserSkillTagOut])
async def update_freelancer_skills(
    skills_data: UserSkillsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    (僅限工作者) 更新技能標籤。
    """
    service = ProfileService(db)
    updated_skills = await service.update_my_skills(current_user, skills_data)
    return updated_skills

@router.get("/freelancer/{user_id}", response_model=FreelancerProfileOut)
async def get_public_freelancer_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    獲取指定 User ID 的工作者公開 Profile
    """
    service = ProfileService(db)
    profile = await service.get_freelancer_profile(user_id)
    return profile

# (新增) 獲取雇主公開 Profile 的端點
@router.get(
    "/employer/{user_id}", 
    response_model=EmployerProfileOut,
    summary="獲取雇主公開檔案 (含評分)"
)
async def get_public_employer_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    (公開) 獲取特定雇主的詳細資料與信譽評分。
    """
    service = ProfileService(db)
    return await service.get_employer_profile_public(user_id)

@router.get(
    "/freelancers/search", 
    response_model=PaginatedFreelancerSearchOut, # (修改) 回傳型別
    summary="搜尋公開的工作者 (分頁)"
)
async def search_public_freelancers(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # (新增) 分頁參數
    page: int = Query(1, ge=1, description="頁碼"),
    size: int = Query(20, ge=1, le=100, description="每頁筆數")
):
    """
    (雇主) 依技能標籤搜尋「公開」的工作者 Profile (分頁)。
    """
    tag_ids_from_query = request.query_params.getlist("tag_id")
    if not tag_ids_from_query:
        tag_ids_from_query = request.query_params.getlist("tag_id[]")
    
    tag_ids = tag_ids_from_query if tag_ids_from_query else None
    
    # 計算 offset
    limit = size
    offset = (page - 1) * size

    service = ProfileService(db)
    # 呼叫 Service (已改為支援分頁)
    result = await service.search_freelancers(
        tag_ids=tag_ids, 
        limit=limit, 
        offset=offset
    )
    
    return result