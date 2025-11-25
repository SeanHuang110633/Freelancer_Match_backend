# app/services/deliverable_service.py

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

# (新增) 匯入儲存層工廠
from app.core.storage import get_storage_provider


from app.models.user import User
from app.models.deliverable import Deliverable
from app.repositories.deliverable_repo import DeliverableRepository
from app.repositories.contract_repo import ContractRepository


logger = logging.getLogger(__name__)

class DeliverableService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DeliverableRepository(db)
        self.contract_repo = ContractRepository(db)
        
        # (新增) 初始化儲存提供者
        # 自動根據 config 決定使用 LocalStorage 或 GCPStorage
        self.storage = get_storage_provider()

    # (移除) _save_upload_file 與 _delete_file 函式已完全移除
    # 相關邏輯已委派給 self.storage

    async def upload_deliverable(
        self,
        contract_id: str,
        user: User,
        file: UploadFile,
        description: str
    ) -> Deliverable:
        """
        業務邏輯：工作者上傳交付物
        """
        # 1. 獲取合約
        contract = await self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "合約不存在")

        # 2. 權限檢查：只有該合約的「自由工作者」可以上傳
        if contract.freelancer_id != user.user_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "只有該合約的自由工作者可以上傳交付物"
            )

        # 3. 狀態檢查 (鎖定機制)
        # 只有「進行中」可以上傳。若為「工作者要求驗收」，則視為已鎖定。
        if contract.status != "進行中":
            detail_msg = "無法上傳交付物"
            if contract.status == "工作者要求驗收":
                detail_msg = "您已請求驗收，檔案目前已鎖定。如需修改，請先「撤回驗收請求」。"
            else:
                detail_msg = f"目前合約狀態為「{contract.status}」，無法上傳交付物。"
            
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail_msg
            )

        # 4. (重構) 儲存檔案 - 使用 StorageProvider
        # 指定目錄為 'deliverables'，實作層會處理實際路徑或 Bucket 路徑
        file_url = await self.storage.save_file(file, directory="deliverables")

        # 5. 建立 DB 紀錄
        new_deliverable = Deliverable(
            contract_id=contract_id,
            uploader_id=user.user_id,
            description=description,
            file_url=file_url,
            acceptance_status="待驗收"
        )
        return await self.repo.create_deliverable(new_deliverable)

    async def get_contract_deliverables(self, contract_id: str, user: User) -> List[Deliverable]:
        # (保持不變)
        contract = await self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "合約不存在")

        # 權限檢查：必須是合約當事人
        if user.user_id != contract.employer_id and user.user_id != contract.freelancer_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "您無權查看此合約的交付物")

        # 隱私控制邏輯：如果是「雇主」且合約狀態仍在「進行中」，則隱藏交付物
        if user.user_id == contract.employer_id and contract.status == "進行中":
            return []

        return await self.repo.list_deliverables_by_contract_id(contract_id)

    async def update_deliverable(
        self,
        deliverable_id: str,
        user: User,
        file: Optional[UploadFile],
        description: str
    ) -> Deliverable:
        """
        業務邏輯：更新交付物 (覆蓋檔案或修改描述)
        """
        # 1. 獲取交付物
        deliverable = await self.repo.get_deliverable_by_id(deliverable_id)
        if not deliverable:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "交付物不存在")

        # 2. 獲取合約 (檢查狀態用)
        contract = await self.contract_repo.get_contract_by_id(deliverable.contract_id)
        
        # 3. 權限檢查
        if deliverable.uploader_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "您無權修改此交付物")

        # 4. 狀態鎖定檢查
        if contract.status != "進行中":
            msg = "檔案目前已鎖定" if contract.status == "工作者要求驗收" else f"合約狀態非進行中 ({contract.status})"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{msg}，無法修改交付物")

        # 5. 驗收狀態檢查 (僅待驗收可改)
        if deliverable.acceptance_status != "待驗收":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "該交付物已被處理 (通過或退回)，無法直接修改")

        # 6. 執行更新
        if description is not None:
            deliverable.description = description

        if file:
            # (重構) 刪除舊檔案
            # StorageProvider 會處理刪除邏輯，若檔案不存在或刪除失敗通常會 log 但不拋出例外
            if deliverable.file_url:
                await self.storage.delete_file(deliverable.file_url)
            
            # (重構) 儲存新檔案
            new_url = await self.storage.save_file(file, directory="deliverables")
            deliverable.file_url = new_url

        return await self.repo.update_deliverable(deliverable)

    async def delete_deliverable(self, deliverable_id: str, user: User):
        """
        業務邏輯：刪除交付物
        """
        # 1. 獲取交付物
        deliverable = await self.repo.get_deliverable_by_id(deliverable_id)
        if not deliverable:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "交付物不存在")

        # 2. 獲取合約
        contract = await self.contract_repo.get_contract_by_id(deliverable.contract_id)

        # 3. 權限檢查
        if deliverable.uploader_id != user.user_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, "您無權刪除此交付物")

        # 4. 狀態鎖定檢查
        if contract.status != "進行中":
            msg = "檔案目前已鎖定" if contract.status == "工作者要求驗收" else f"合約狀態非進行中 ({contract.status})"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{msg}，無法刪除交付物")

        # 5. 驗收狀態檢查
        if deliverable.acceptance_status != "待驗收":
             raise HTTPException(status.HTTP_400_BAD_REQUEST, "該交付物已被處理，無法刪除")

        # 6. 執行刪除 (重構) 
        if deliverable.file_url:
            await self.storage.delete_file(deliverable.file_url)
            
        await self.repo.delete_deliverable(deliverable)