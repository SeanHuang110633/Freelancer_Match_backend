# app/services/proposal_service.py

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging


# (新增) 匯入儲存層工廠
from app.core.storage import get_storage_provider

from app.models.user import User, UserRoleEnum
from app.models.proposal import Proposal
from app.models.project import Project
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.proposal_schema import ProposalCreate
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class ProposalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.proposal_repo = ProposalRepository(db)
        self.project_repo = ProjectRepository(db)
        self.notification_service = NotificationService(db)
        
        # (新增) 初始化儲存提供者
        # 這會根據 config 自動決定是 LocalStorage 還是 GCPStorage
        self.storage = get_storage_provider() 

    # (移除) _save_upload_file 與 _delete_file 函式已完全移除
    # 相關邏輯已封裝至 app/core/storage/ 下的實作類別中

    async def create_proposal(
        self,
        project_id: str,
        freelancer: User,
        proposal_data: ProposalCreate,
        attachment: Optional[UploadFile]
    ) -> Proposal:
        if freelancer.role != UserRoleEnum.freelancer:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有自由工作者可以提案")

        project = await self.project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案件不存在")
        
        if project.status != "招募中":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="此案件目前未在招募中")

        existing = await self.proposal_repo.check_existing_proposal(project_id, freelancer.user_id)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="你已經對此案件提案")

        attachment_url = None
        if attachment:
            # (重構) 使用 Storage Provider
            # 這裡直接指定目錄名稱 'proposals'，實作細節由 storage layer 處理
            # 回傳的會是完整的公開 URL 或相對路徑
            attachment_url = await self.storage.save_file(attachment, directory="proposals")

        new_proposal = Proposal(
            project_id=project_id,
            freelancer_id=freelancer.user_id,
            brief_description=proposal_data.brief_description,
            attachment_url=attachment_url,
            status="已提交"
        )

        await self.notification_service.create_notification(
            user_id=project.employer_id,
            title=f"案件「{project.title}」收到新提案",
            message=f"來自 {freelancer.email} 的提案。",
            link_url=f"/projects/{project.project_id}/proposals"
        )

        created_proposal = await self.proposal_repo.create_proposal(new_proposal)
        return created_proposal

    async def delete_proposal(self, proposal_id: str, current_user: User) -> None:
        proposal = await self.proposal_repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")

        if proposal.freelancer_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限刪除此提案")

        if proposal.status not in ["已提交", "雇主已撤銷案件"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提案已被處理，無法撤回")

        # (重構) 使用 Storage Provider 刪除檔案
        if proposal.attachment_url:
            await self.storage.delete_file(proposal.attachment_url)

        await self.proposal_repo.delete_proposal(proposal)
        return

    async def update_proposal(
        self,
        proposal_id: str,
        user: User,
        brief_description: str,
        attachment: Optional[UploadFile]
    ) -> Proposal:
        proposal = await self.proposal_repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")

        if proposal.freelancer_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限修改此提案")

        if proposal.status != "已提交":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提案已被處理，無法修改")

        proposal.brief_description = brief_description

        if attachment:
            # 1. (重構) 上傳新檔案
            new_attachment_url = await self.storage.save_file(attachment, directory="proposals")
            
            # 2. (重構) 刪除舊檔案
            if proposal.attachment_url:
                # 不論舊檔案是在 Local 還是 GCS，StorageProvider 會根據 URL 前綴判斷是否能刪除
                # 或是我們假設切換環境後，舊環境的檔案可能無法透過新 Provider 刪除
                # 但基於介面設計，我們直接呼叫 delete_file 即可，失敗通常會被 log 下來但不中斷
                await self.storage.delete_file(proposal.attachment_url)
            
            # 3. 更新 DB
            proposal.attachment_url = new_attachment_url

        return await self.proposal_repo.update_proposal(proposal)

    # ... (其餘 read-only 方法如 get_proposal_details, get_project_with_proposals, update_proposal_status 保持不變) ...
    
    async def get_proposal_details(self, proposal_id: str, user: User) -> Proposal:
        # (保持不變)
        proposal = await self.proposal_repo.get_proposal_by_id_with_details(proposal_id)
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")
        if proposal.freelancer_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限檢視此提案")
        return proposal

    async def get_project_with_proposals(self, project_id: str, employer: User) -> Project:
        # (保持不變)
        project = await self.project_repo.get_project_by_id_with_proposals(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案件不存在")
        if project.employer_id != employer.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限檢視此案件的提案")
        return project

    async def update_proposal_status(self, proposal_id: str, new_status: str, employer: User) -> Proposal:
        # (保持不變)
        if new_status not in ["已接受", "已拒絕"]:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無效的狀態")

        proposal = await self.proposal_repo.get_proposal_by_id_with_project(proposal_id)
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")
        if proposal.project.employer_id != employer.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限修改此提案")
        if proposal.status != "已提交":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="此提案已被處理")

        proposal.status = new_status
        
        # (通知邏輯保持不變)
        if new_status == "已接受":
            await self.notification_service.create_notification(
                user_id=proposal.freelancer_id,
                title=f"恭喜！您的提案「{proposal.project.title}」已被接受",
                link_url=f"/my-contracts"
            )
        elif new_status == "已拒絕":
             await self.notification_service.create_notification(
                user_id=proposal.freelancer_id,
                title=f"遺憾，您的提案「{proposal.project.title}」未被接受",
                link_url=f"/find-jobs"
            )
        return await self.proposal_repo.update_proposal(proposal)