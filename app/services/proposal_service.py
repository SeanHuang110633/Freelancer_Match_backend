# app/services/proposal_service.py

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import aiofiles
import uuid
import os
from typing import List, Optional

from app.models.user import User, UserRoleEnum
from app.models.proposal import Proposal
from app.models.project import Project
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.proposal_schema import ProposalCreate

from app.services.notification_service import NotificationService # (M8.3 新增)
# (修正) 移除重複的 import
# from app.repositories.project_repo import ProjectRepository

# --- 檔案上傳設定 (保持不變) ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "proposals"
UPLOAD_URL_PREFIX = "/static/uploads/proposals/"
os.makedirs(UPLOAD_DIR, exist_ok=True)
# --- 結束 ---


class ProposalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.proposal_repo = ProposalRepository(db)
        self.project_repo = ProjectRepository(db) 
        self.notification_service = NotificationService(db) # (M8.3 新增)

    # ... _save_upload_file (保持不變) ...
    async def _save_upload_file(self, file: UploadFile) -> str:
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="附件僅支援 PDF 格式"
            )
        file_extension = ".pdf"
        filename = f"{uuid.uuid4()}{file_extension}"
        file_path = UPLOAD_DIR / filename
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"檔案儲存失敗: {str(e)}"
            )
        return f"{UPLOAD_URL_PREFIX}{filename}"

    # --- ( M8.3 執行順序修正 ) ---
    async def create_proposal(
        self, 
        project_id: str, 
        freelancer: User, 
        proposal_data: ProposalCreate, 
        attachment: Optional[UploadFile]
    ) -> Proposal:
        if freelancer.role != UserRoleEnum.freelancer:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有自由工作者可以提案")
        
        # 步驟 1: 驗證 (保持不變)
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
            attachment_url = await self._save_upload_file(attachment)

        # 步驟 2: (修正) 僅在記憶體中建立物件
        new_proposal = Proposal(
            project_id=project_id,
            freelancer_id=freelancer.user_id,
            brief_description=proposal_data.brief_description,
            attachment_url=attachment_url,
            status="已提交"
        )

        # 步驟 3: (修正) 先呼叫通知 (將 Notification 加入 Session)
        await self.notification_service.create_notification(
            user_id=project.employer_id, # 接收方：雇主
            title=f"案件「{project.title}」收到新提案",
            message=f"來自 {freelancer.email} 的提案。", # (修正) 避免暴露敏感資訊，或使用 freelancer.full_name
            link_url=f"/projects/{project.project_id}/proposals" # 前端提案管理頁
        )
        
        # 步驟 4: (修正) 最後才呼叫 Repo 儲存
        # (這會將 Proposal 和 Notification 一起提交)
        created_proposal = await self.proposal_repo.create_proposal(new_proposal)
        
        return created_proposal
    # --- ( M8.3 修正結束 ) ---

    # ... delete_proposal (保持不變) ...
    async def delete_proposal(self, proposal_id: str, current_user: User) -> None:
        proposal = await self.proposal_repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")
        if proposal.freelancer_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限刪除此提案")
        if proposal.status != "已提交":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提案已被處理，無法撤回")
        if proposal.attachment_url:
            file_path = BASE_DIR / proposal.attachment_url.lstrip('/')
            if os.path.exists(file_path):
                os.remove(file_path)
        await self.proposal_repo.delete_proposal(proposal)
        return

    # ... get_project_with_proposals (保持不變) ...
    async def get_project_with_proposals(self, project_id: str, employer: User) -> Project:
        project = await self.project_repo.get_project_by_id_with_proposals(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案件不存在")
        if project.employer_id != employer.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限檢視此案件的提案")
        return project

    # --- ( M7 邏輯修正 ) ---
    async def update_proposal_status(self, proposal_id: str, new_status: str, employer: User) -> Proposal:
        """
        (雇主) 選擇或拒絕人選 (Use Case 6.3, 6.5)
        """
        if new_status not in ["已接受", "已拒絕"]:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無效的狀態")

        proposal = await self.proposal_repo.get_proposal_by_id_with_project(proposal_id)
        
        if not proposal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提案不存在")

        if proposal.project.employer_id != employer.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你沒有權限修改此提案")
            
        if proposal.status != "已提交":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="此提案已被處理")

        # 步驟 1: 更新物件狀態 (記憶體中)
        proposal.status = new_status
        
        if new_status == "已接受":
            # --- ( M7 邏輯修正 ) ---
            # 根據 M7 新邏輯， '已成案' 狀態應在 M7 (合約 '進行中') 才設定
            # proposal.project.status = "已成案" # <-- (移除此行)
            # --- ( M7 修正結束 ) ---
            
            # 步驟 2: 呼叫通知 (加入 Session)
            await self.notification_service.create_notification(
                user_id=proposal.freelancer_id, # 接收方：工作者
                title=f"恭喜！您的提案「{proposal.project.title}」已被接受",
                link_url=f"/my-contracts" # 提醒他去查看即將產生的合約
            )
            
        elif new_status == "已拒絕":
             # 步驟 2: 呼叫通知 (加入 Session)
             await self.notification_service.create_notification(
                user_id=proposal.freelancer_id, # 接收方：工作者
                title=f"遺憾，您的提案「{proposal.project.title}」未被接受",
                link_url=f"/find-jobs" # 導向回案件列表
            )
             
        # 步驟 3: 最後儲存 (提交所有變更)
        return await self.proposal_repo.update_proposal(proposal)