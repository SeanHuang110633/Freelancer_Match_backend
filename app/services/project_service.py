# app/services/project_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Optional

# 匯入 Models
from app.models.user import User
from app.models.project import Project

# 匯入 Schemas
from app.schemas.project_schema import ProjectCreate, ProjectUpdate

# 匯入 Repositories
from app.repositories.project_repo import ProjectRepository
from app.repositories.skill_tag_repo import SkillTagRepository

class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.skill_tag_repo = SkillTagRepository(db) # 用於驗證 tag

    async def create_project(self, project_data: ProjectCreate, user: User) -> Project:
        """
        業務邏G輯：建立案件
        """
        
        # 1. 權限驗證：必須是雇主
        if user.role != "雇主":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有雇主可以刊登案件"
            )
            
        # 2. 資料校驗：驗證 skill_tag_ids 是否都存在
        if project_data.skill_tag_ids:
            valid_tags_count = await self.skill_tag_repo.count_tags_by_ids(
                project_data.skill_tag_ids
            )
            if valid_tags_count != len(project_data.skill_tag_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="包含無效的技能標籤 ID"
                )
        
        # 3. 執行 Repository 建立
        new_project = await self.project_repo.create_project(
            project_data=project_data,
            employer_id=user.user_id
        )
        
        return new_project

    async def search_projects(
        self,
        tag_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        work_type: Optional[str] = None
    ) -> List[Project]:
        """
        業務邏輯：搜尋案件
        (目前 MVP 階段，業務邏輯主要在 Repository 的查詢中)
        """
        # 根據需求，搜尋條件包含 技能、地區、工作型態
        projects = await self.project_repo.list_projects(
            tag_ids=tag_ids,
            location=location,
            work_type=work_type
        )
        return projects

    async def get_project_details(self, project_id: str) -> Project:
        """
        業務邏輯：獲取單一案件詳情
        """
        project = await self.project_repo.get_project_by_id(project_id)
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="案件不存在"
            )
        return project

    # (新增) 獲取當前雇主刊登的所有案件
    async def get_my_projects(self, user: User) -> List[Project]:
        """
        業務邏輯：獲取當前雇主刊登的所有案件
        """
        if user.role != "雇主":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有雇主可以查看自己刊登的案件"
            )
        
        projects = await self.project_repo.list_projects_by_employer_id(user.user_id)
        return projects
    # (我們暫時先不實作 Update 和 Delete，專注於 MVP)