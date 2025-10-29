import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

# 匯入核心依賴
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

# 匯入 Service 和 Schemas
from app.services.project_service import ProjectService
from app.schemas.project_schema import ProjectCreate, ProjectOut

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects",
    tags=["Projects & Jobs"],
    # (重要) 該模組下的所有 API 都至少需要登入
    dependencies=[Depends(get_current_user)] 
)

@router.post(
    "/", 
    response_model=ProjectOut, 
    status_code=status.HTTP_201_CREATED
)
async def create_new_project(
    project_data: ProjectCreate, # Request Body
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    刊登新案件 (需求)。
    
    - (權限) 僅限「雇主」角色。
    - (資料) 需傳入案件基本資料及所需技能 `skill_tag_ids` 列表。
    """
    service = ProjectService(db)
    
    # Service 層會自動處理權限 (403) 和 標籤驗證 (400)
    new_project = await service.create_project(
        project_data=project_data, 
        user=current_user
    )
    
    return new_project

@router.get("/", response_model=List[ProjectOut])
async def search_all_projects(
    # (新增) 注入 Request 物件
    request: Request,
    db: AsyncSession = Depends(get_db), 
    
    # (重要) 定義複合式搜尋的 Query Parameters
    
    # 2. 地區 (模糊)
    location: Optional[str] = None,
    
    # 3. 工作型態 (精確)
    work_type: Optional[str] = None
):
    """
    搜尋/篩選案件 (工作者使用)。
    
    支援依 技能標籤 (多選)、地區 (模糊)、工作型態 (精確) 進行篩選。
    """
    

    # (修改) 手動從 request.query_params 讀取 'tag_id[]'
    # .getlist() 會自動處理多個同名參數並返回列表
    tag_ids_from_query = request.query_params.getlist("tag_id[]")
    
    # (轉換) 如果列表為空，則設為 None，以便 Service/Repo 處理
    tag_ids = tag_ids_from_query if tag_ids_from_query else None

    # (更新日誌) 打印手動解析的結果
    logger.info(f"Router received query params manually - tag_ids: {tag_ids}, location: {location}, work_type: {work_type}")
    
    service = ProjectService(db)
    projects = await service.search_projects(
        tag_ids=tag_ids,
        location=location,
        work_type=work_type
    )
    
    return projects

@router.get("/my", response_model=List[ProjectOut])
async def read_my_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    獲取當前登入雇主自己刊登的所有案件列表。
    """
    service = ProjectService(db)
    # Service 層會處理角色驗證
    my_projects = await service.get_my_projects(current_user)
    return my_projects


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project_by_id(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    獲取單一案件的詳細資料。
    """
    service = ProjectService(db)
    
    # Service 層會自動處理 404 Not Found
    project = await service.get_project_details(project_id)
    
    return project

