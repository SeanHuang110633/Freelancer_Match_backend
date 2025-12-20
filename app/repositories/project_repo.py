# app/repositories/project_repo.py
import logging
import uuid
import json 
from fastapi.encoders import jsonable_encoder 
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from app.models.user import User
from app.models.employer_profile import EmployerProfile

# (快取功能) 匯入 Cache 與 Redis
from pydantic import TypeAdapter 
from app.core.cache import cached
from app.core.redis import redis_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from sqlalchemy import func, delete 
from fastapi import HTTPException

# 匯入 Models
from app.models.project import Project, ProjectSkillTag
from app.models.user import User
from app.models.proposal import Proposal 

# 匯入 Schemas
from app.schemas.project_schema import ProjectCreate, ProjectUpdate, ProjectOut

class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ... (create_project, get_project_by_id, get_project_by_id_with_proposals, get_project_view 保持不變) ...
    async def create_project(self, project_data: ProjectCreate, employer_id: str) -> Project:
        project_dict = project_data.model_dump(exclude={"skill_tag_ids"})
        new_project_id = str(uuid.uuid4())
        
        db_project = Project(
            **project_dict,
            project_id=new_project_id,
            employer_id=employer_id
        )
        
        db_skill_tags = []
        for tag_id in project_data.skill_tag_ids:
            db_skill_tags.append(
                ProjectSkillTag(
                    project_skill_tag_id=str(uuid.uuid4()),
                    project_id=new_project_id,
                    tag_id=tag_id
                )
            )
            
        self.db.add(db_project)
        self.db.add_all(db_skill_tags)
        
        await self.db.commit()
        # (注意) 搜尋改為分頁且移除快取後，這裡其實不需要清除 "project:list:*" 了
        # 但保留也無妨，避免有其他地方用到
        await redis_manager.delete_keys_by_pattern("project:list:*")
        
        complete_project = await self.get_project_by_id(new_project_id)
        if complete_project is None:
            raise HTTPException(status_code=404, detail="剛建立的案件找不到")

        return complete_project 

    async def get_project_by_id(self, project_id: str) -> Project | None:
        stmt = select(Project).where(Project.project_id == project_id)
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_project_by_id_with_proposals(self, project_id: str) -> Project | None:
        stmt = select(Project).where(Project.project_id == project_id).options(
            joinedload(Project.employer).
            selectinload(User.employer_profile),
            selectinload(Project.skills).
            joinedload(ProjectSkillTag.tag),
            selectinload(Project.proposals).options(
                selectinload(Proposal.freelancer).options(
                    selectinload(User.freelancer_profile)
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_project_view(self, project_id: str) -> Optional[ProjectOut]:
        cache_key = f"project:view:{project_id}"
        cached_data = await redis_manager.get_value(cache_key)
        if cached_data:
            try:
                return ProjectOut.model_validate_json(cached_data)
            except Exception as e:
                logger.error(f"Cache deserialize failed for {cache_key}: {e}")
        
        project = await self.get_project_by_id(project_id)
        if not project:
            return None
            
        project_out = ProjectOut.model_validate(project)
        try:
            data_dict = jsonable_encoder(project_out)
            json_str = json.dumps(data_dict)
            await redis_manager.set_value(cache_key, json_str, expire=300)
        except Exception as e:
            logger.error(f"Cache write failed for {cache_key}: {e}")
            
        return project_out

    # 條件搜尋案件 (分頁版)
    # (修改) 移除 @cached，加入 limit, offset
    async def list_projects(
        self,
        tag_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        work_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Project]:
        """
        (核心功能) 依條件複合式搜尋案件 (分頁)
        """
        stmt = select(Project)

        # Eager Load
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile),
            selectinload(Project.skills).
            joinedload(ProjectSkillTag.tag) # (確保技能被載入)
        )

        if tag_ids:
            logger.info(f"Applying tag_ids filter (match ALL): {tag_ids}")
            subq = (
                select(ProjectSkillTag.project_id)
                .where(ProjectSkillTag.tag_id.in_(tag_ids))
                .group_by(ProjectSkillTag.project_id)
                .having(func.count(func.distinct(ProjectSkillTag.tag_id)) == len(tag_ids))
                .subquery()
            )
            stmt = stmt.where(Project.project_id.in_(select(subq.c.project_id)))

        if location:
            logger.info(f"Applying location filter: {location}")
            stmt = stmt.where(Project.location.ilike(f"%{location}%"))

        if work_type:
            logger.info(f"Applying work_type filter: {work_type}")
            stmt = stmt.where(Project.work_type == work_type)

        # 分頁查詢
        result = await self.db.execute(stmt.distinct().limit(limit).offset(offset))
        return result.scalars().all()

    # (新增) 計算搜尋結果總數
    async def count_projects(
        self,
        tag_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        work_type: Optional[str] = None
    ) -> int:
        """
        計算符合條件的案件總數
        """
        # 使用 count(distinct id) 避免因 join 造成的重複計算
        stmt = select(func.count(func.distinct(Project.project_id)))

        if tag_ids:
            subq = (
                select(ProjectSkillTag.project_id)
                .where(ProjectSkillTag.tag_id.in_(tag_ids))
                .group_by(ProjectSkillTag.project_id)
                .having(func.count(func.distinct(ProjectSkillTag.tag_id)) == len(tag_ids))
                .subquery()
            )
            stmt = stmt.where(Project.project_id.in_(select(subq.c.project_id)))

        if location:
            stmt = stmt.where(Project.location.ilike(f"%{location}%"))

        if work_type:
            stmt = stmt.where(Project.work_type == work_type)

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ... (list_active_projects_with_skills, list_projects_by_employer_id 保持不變) ...
    async def list_active_projects_with_skills(self) -> List[Project]:
        stmt = select(Project).where(Project.status == '招募中')
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def list_projects_by_employer_id(self, employer_id: str) -> List[Project]:
        stmt = select(Project).where(Project.employer_id == employer_id).order_by(Project.created_at.desc())
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def update_project(self, project: Project) -> Project:
        await self.db.commit()
        await self.db.refresh(project)
        # (注意) 搜尋改為分頁且移除快取後，這裡其實不需要清除 "project:list:*" 了
        await redis_manager.delete_keys_by_pattern("project:list:*")
        await redis_manager.delete_key(f"project:view:{project.project_id}")

        logger.info(f"Cleared cache for project:view:{project.project_id} after update")
        refreshed_project = await self.get_project_by_id(project.project_id)
        logger.info(f"Re-fetched project after update: {refreshed_project}")
        if refreshed_project is None:
            raise HTTPException(status_code=500, detail="Failed to re-fetch project after update")
        return refreshed_project

    async def update_project_skills(self, project_id: str, tag_ids: List[str]):
        stmt_delete = delete(ProjectSkillTag).where(
            ProjectSkillTag.project_id == project_id
        )
        await self.db.execute(stmt_delete)
        await self.db.flush()

        new_skill_links = []
        for tag_id in tag_ids:
            new_skill_links.append(
                ProjectSkillTag(
                    project_skill_tag_id=str(uuid.uuid4()),
                    project_id=project_id,
                    tag_id=tag_id
                )
            )
        
        if new_skill_links:
            self.db.add_all(new_skill_links)