# app/services/project_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List, Optional

# 匯入 Models
from app.models.user import User
from app.models.project import Project

# 匯入 Schemas
from app.schemas.project_schema import ProjectCreate, ProjectUpdate, ProjectStatusUpdate

# 匯入 Repositories
from app.repositories.project_repo import ProjectRepository
from app.repositories.skill_tag_repo import SkillTagRepository
from app.repositories.proposal_repo import ProposalRepository
from app.services.notification_service import NotificationService

class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.skill_tag_repo = SkillTagRepository(db) # 用於驗證 tag
        self.proposal_repo = ProposalRepository(db) # 用於處理提案相關邏輯
        self.notification_service = NotificationService(db) # 用於發送通知

    # (新增) 輔助函式：檢查權限和狀態
    async def _get_and_check_permission(
        self, project_id: str, user: User, allow_statuses: List[str]
    ) -> Project:
        """
        獲取案件，檢查是否為擁有者，並檢查是否處於允許的狀態。
        """
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

    # (新增) 需求二：更新案件內容
    async def update_project(
        self, project_id: str, data: ProjectUpdate, user: User
    ) -> Project:
        """
        業務邏輯：更新案件內容 (僅限招募中)
        """
        # 1. 獲取並檢查權限
        project = await self._get_and_check_permission(
            project_id, user, allow_statuses=["招募中"]
        )

        # 2. 更新欄位
        update_data = data.model_dump(exclude_unset=True)
        skill_tag_ids = update_data.pop("skill_tag_ids", None)

        for key, value in update_data.items():
            if hasattr(project, key):
                setattr(project, key, value)

        # 3. (可選) 更新技能
        if skill_tag_ids is not None:
            # 驗證 tag IDs
            if skill_tag_ids:
                valid_tags_count = await self.skill_tag_repo.count_tags_by_ids(skill_tag_ids)
                if valid_tags_count != len(skill_tag_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="包含無效的技能標籤 ID"
                    )
            # 呼叫 Repo 更新技能
            await self.project_repo.update_project_skills(project_id, skill_tag_ids)

        # 4. 儲存變更 (Repo 會 commit)
        updated_project = await self.project_repo.update_project(project)

        # 5. (通知) 獲取所有提案者並發送通知
        # (我們需要 proposals，所以重新載入一次)
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

        return updated_project

    # (新增) 需求二：更新案件狀態 (關閉案件)
    async def update_project_status(
        self, project_id: str, data: ProjectStatusUpdate, user: User
    ) -> Project:
        """
        業務邏輯：更新案件狀態 (僅限 招募中 -> 已關閉)
        """
        new_status = data.status
        if new_status != "已關閉":
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此 API 僅支援將狀態更新為「已關閉」"
            )

        # 1. 獲取並檢查權限
        project = await self._get_and_check_permission(
            project_id, user, allow_statuses=["招募中"]
        )

        # 2. 更新狀態
        project.status = new_status
        updated_project = await self.project_repo.update_project(project)

        # 3. (連帶更新提案) 獲取所有提案者，更新其狀態並發送通知
        project_with_proposals = await self.project_repo.get_project_by_id_with_proposals(project_id)
        if project_with_proposals and project_with_proposals.proposals:
            title = f"案件關閉通知：{project.title[:20]}..."
            message = "您提案的案件已被雇主關閉。"
            link_url = f"/projects/{project_id}" # (或導向 /my-proposals)

            for proposal in project_with_proposals.proposals:
                if proposal.status == "已提交":
                    # (重要) 更新提案狀態
                    proposal.status = "雇主已撤銷案件" # 使用你指定的狀態
                    await self.proposal_repo.update_proposal(proposal)
                    
                    # 發送通知
                    await self.notification_service.create_notification(
                        user_id=proposal.freelancer_id,
                        title=title,
                        message=message,
                        link_url=link_url
                    )

        return updated_project
    
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