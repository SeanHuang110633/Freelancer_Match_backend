# app/routers/project_router.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

# 匯入核心依賴
from app.core.database import get_db, AsyncSessionLocal
from app.core.redis import redis_manager
from app.core.security import get_current_user
from app.models.user import User

# 匯入 Service 和 Schemas
from app.services.project_service import ProjectService
from app.schemas.project_schema import (
    ProjectCreate, ProjectOut, ProjectUpdate, ProjectStatusUpdate,
    PaginatedProjectSearchOut # (新增)
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects",
    tags=["Projects & Jobs"],
    dependencies=[Depends(get_current_user)] 
)

@router.post(
    "/", 
    response_model=ProjectOut, 
    status_code=status.HTTP_201_CREATED
)
async def create_new_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    刊登新案件 (需求)。
    """
    service = ProjectService(db)
    new_project = await service.create_project(
        project_data=project_data, 
        user=current_user
    )
    return new_project

@router.get(
    "/", 
    response_model=PaginatedProjectSearchOut, # (修改) 回傳型別
    summary="搜尋/篩選案件 (分頁)"
)
async def search_all_projects(
    request: Request,
    db: AsyncSession = Depends(get_db), 
    location: Optional[str] = None,
    work_type: Optional[str] = None,
    # (新增) 分頁參數
    page: int = Query(1, ge=1, description="頁碼"),
    size: int = Query(20, ge=1, le=100, description="每頁筆數")
):
    """
    搜尋/篩選案件 (工作者使用)。
    支援依 技能標籤 (多選)、地區 (模糊)、工作型態 (精確) 進行篩選。
    """
    
    tag_ids_from_query = request.query_params.getlist("tag_id")
    if not tag_ids_from_query:
        tag_ids_from_query = request.query_params.getlist("tag_id[]")

    tag_ids = tag_ids_from_query if tag_ids_from_query else None

    logger.info(f"Router received params - tag_ids: {tag_ids}, location: {location}, work_type: {work_type}, page: {page}, size: {size}")
    
    # 計算 offset
    limit = size
    offset = (page - 1) * size

    service = ProjectService(db)
    result = await service.search_projects(
        tag_ids=tag_ids,
        location=location,
        work_type=work_type,
        limit=limit,
        offset=offset
    )
    
    return result

@router.get("/my", response_model=List[ProjectOut])
async def read_my_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    獲取當前登入雇主自己刊登的所有案件列表。
    """
    service = ProjectService(db)
    my_projects = await service.get_my_projects(current_user)
    return my_projects

# @router.get("/{project_id}", response_model=ProjectOut)
# async def get_project_by_id(
#     project_id: str,
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     獲取單一案件的詳細資料。
#     """
#     logger.info(f"這邊一次?: {project_id}")
#     service = ProjectService(db)
#     project = await service.get_project_details(project_id)
#     return project

@router.get("/{project_id}", response_model=ProjectOut)
async def get_project_detail(
    project_id: str,
    # ❌ 移除這裡的 db 依賴注入，避免一進來就佔用連線
    # db: AsyncSession = Depends(get_db) 
):
    """
    獲取案件詳情 (Lazy Loading 優化版)
    - 先查 Redis 快取
    - 快取未命中才建立 DB 連線
    """
    
    # 1. 嘗試從 Redis 讀取
    # 假設您的 Service 有封裝好 get_cached_project，或者直接用 redis_manager
    # 這裡示範直接在 Router 層做控制，或呼叫 Service 的 cache 方法
    
    # 為了保持 Router 乾淨，建議將邏輯封裝在 Service 的靜態方法或不依賴 DB 的方法中
    # 但這裡為了明確展示 Lazy Loading 邏輯，我寫得比較直觀一點：
    
    # 假設 project_service 可以不需要 db 初始化 (詳見下方 Service 修改)
    # 或者我們手動操作 Redis
    logger.info(f"這邊又一次?: {project_id}")
    cache_key = f"project:view:{project_id}"
    cached_data = await redis_manager.get_value(cache_key)
    
    if cached_data:
        #若有快取，直接回傳 (完全不消耗 DB 連線)
        return ProjectOut.model_validate_json(cached_data)

    # 2. Redis 沒資料 (Cache Miss)，才建立 DB 連線
    async with AsyncSessionLocal() as db:
        project_service = ProjectService(db)
        project = await project_service.get_project_details(project_id)
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
            
        # 3. 寫入快取 (由 Service 內部處理，或在這裡處理)
        # Service 的 get_project_by_id 通常已經包含了「查 DB + 寫 Redis」的邏輯
        # 所以這裡我們只需要呼叫它即可
        
        return project


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project_details(
    project_id: str,
    project_data: ProjectUpdate, # Request Body
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 更新「招募中」案件的詳細內容。
    """
    service = ProjectService(db)
    # (重要) 確保 project_service.py 中也有 update_project 方法
    updated_project = await service.update_project( 
        project_id=project_id,
        data=project_data,
        user=current_user
    )
    return updated_project


@router.patch("/{project_id}/status", response_model=ProjectOut)
async def update_project_status(
    project_id: str,
    status_data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 更新案件狀態。
    """
    service = ProjectService(db)
    updated_project = await service.update_project_status(
        project_id=project_id,
        data=status_data,
        user=current_user
    )
    return updated_project