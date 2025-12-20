# app/services/project_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Optional
import logging

# 匯入 Cache 相關模組
from app.core.cache import cached
from app.core.redis import redis_manager  # [修正] 新增匯入 redis_manager 用於清除快取

# 匯入 Models
from app.models.user import User
from app.models.project import Project

# 匯入 Schemas
from app.schemas.project_schema import ProjectCreate, ProjectUpdate, ProjectStatusUpdate, ProjectOut

# 匯入 Repositories
from app.repositories.project_repo import ProjectRepository
from app.repositories.skill_tag_repo import SkillTagRepository
from app.repositories.proposal_repo import ProposalRepository
from app.services.notification_service import NotificationService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.skill_tag_repo = SkillTagRepository(db) 
        self.proposal_repo = ProposalRepository(db) 
        self.notification_service = NotificationService(db)

    async def _get_and_check_permission(
        self, project_id: str, user: User, allow_statuses: List[str]
    ) -> Project:
        project = await self.project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="案件不存在"
            )
        if project.employer_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="你沒有權限修改此案件"
            )
        if project.status not in allow_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"此案件狀態為「{project.status}」，無法執行此操作"
            )
        return project

    async def update_project(
        self, project_id: str, data: ProjectUpdate, user: User
    ) -> Project:
        project = await self._get_and_check_permission(
            project_id, user, allow_statuses=["招募中"]
        )

        update_data = data.model_dump(exclude_unset=True)
        skill_tag_ids = update_data.pop("skill_tag_ids", None)

        for key, value in update_data.items():
            if hasattr(project, key):
                setattr(project, key, value)
        
        logger.info(f"Updating project {project_id} with data: {update_data} and skill_tag_ids: {skill_tag_ids}")

        if skill_tag_ids is not None:
            if skill_tag_ids:
                logger.info(f"Validating skill_tag_ids: {skill_tag_ids}")
                valid_tags_count = await self.skill_tag_repo.count_tags_by_ids(skill_tag_ids)
                if valid_tags_count != len(skill_tag_ids):
                    logger.error(f"Invalid skill_tag_ids provided: {skill_tag_ids}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="包含無效的技能標籤 ID"
                    )
                logger.info(f"Skill_tag_ids are valid: {skill_tag_ids}")
            await self.project_repo.update_project_skills(project_id, skill_tag_ids)
        logger.info(f"Committing updates to project {project_id}")
        updated_project = await self.project_repo.update_project(project)

        # [修正] 使用 delete_key 替代 delete (RedisManager 方法名修正)
        await redis_manager.delete_key(f"project:view:{project_id}")
        logger.info(f"清除 project:view:{project_id} after update")
        project_with_proposals = await self.project_repo.get_project_by_id_with_proposals(project_id)
        if project_with_proposals and project_with_proposals.proposals:
            title = f"案件更新通知：{project.title[:20]}..."
            message = "您提案的案件內容已被雇主更新，請前往查看。"
            link_url = f"/projects/{project_id}"
            
            notified_users = set()
            for proposal in project_with_proposals.proposals:
                if proposal.status == "已提交" and proposal.freelancer_id not in notified_users:
                    await self.notification_service.create_notification(
                        user_id=proposal.freelancer_id,
                        title=title,
                        message=message,
                        link_url=link_url
                    )
                    notified_users.add(proposal.freelancer_id)
        logger.info(f"Cleared cache for project:view:{project_id} after update")    
        return updated_project

    async def update_project_status(
        self, project_id: str, data: ProjectStatusUpdate, user: User
    ) -> Project:
        new_status = data.status
        if new_status != "已關閉":
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此 API 僅支援將狀態更新為「已關閉」"
            )

        project = await self._get_and_check_permission(
            project_id, user, allow_statuses=["招募中"]
        )

        project.status = new_status
        updated_project = await self.project_repo.update_project(project)

        # [修正] 使用 delete_key 替代 delete (RedisManager 方法名修正)
        await redis_manager.delete_key(f"project:view:{project_id}")

        project_with_proposals = await self.project_repo.get_project_by_id_with_proposals(project_id)
        if project_with_proposals and project_with_proposals.proposals:
            title = f"案件關閉通知：{project.title[:20]}..."
            message = "您提案的案件已被雇主關閉。"
            link_url = f"/projects/{project_id}" 

            for proposal in project_with_proposals.proposals:
                if proposal.status == "已提交":
                    proposal.status = "雇主已撤銷案件" 
                    await self.proposal_repo.update_proposal(proposal)
                    
                    await self.notification_service.create_notification(
                        user_id=proposal.freelancer_id,
                        title=title,
                        message=message,
                        link_url=link_url
                    )

        return updated_project
    
    async def create_project(self, project_data: ProjectCreate, user: User) -> Project:
        if user.role != "雇主":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有雇主可以刊登案件"
            )
            
        if project_data.skill_tag_ids:
            valid_tags_count = await self.skill_tag_repo.count_tags_by_ids(
                project_data.skill_tag_ids
            )
            if valid_tags_count != len(project_data.skill_tag_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="包含無效的技能標籤 ID"
                )
        
        new_project = await self.project_repo.create_project(
            project_data=project_data,
            employer_id=user.user_id
        )
        
        return new_project

    async def search_projects(
        self,
        tag_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        work_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> dict: # { items, total }
        """
        業務邏輯：搜尋案件 (分頁)
        """
        projects = await self.project_repo.list_projects(
            tag_ids=tag_ids,
            location=location,
            work_type=work_type,
            limit=limit,
            offset=offset
        )
        total = await self.project_repo.count_projects(
            tag_ids=tag_ids,
            location=location,
            work_type=work_type
        )
        return {"items": projects, "total": total}

    @cached(key_prefix="project:view", expire=3600, namespace="project_id")
    async def get_project_details(self, project_id: str) -> ProjectOut:
        project = await self.project_repo.get_project_view(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="案件不存在"
            )
        return project

    async def get_my_projects(self, user: User) -> List[Project]:
        if user.role != "雇主":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有雇主可以查看自己刊登的案件"
            )
        
        projects = await self.project_repo.list_projects_by_employer_id(user.user_id)
        return projects