# app/routers/contract_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

# 匯入 M7
from app.services.contract_service import ContractService
from app.schemas.contract_schema import (
    ContractCreate, ContractUpdate, ContractStatusUpdate, ContractOut
)

# 匯入 M1 (Auth)
from app.models.user import User
from app.core.security import get_current_user # 依賴注入：獲取當前使用者
from app.core.database import get_db # 依賴注入：獲取 DB Session

router = APIRouter(
    prefix="/contracts",
    tags=["Contracts"] # API 文件分組
)

# 輔助函式：在路由中快速實例化 Service
def get_contract_service(db: AsyncSession = Depends(get_db)) -> ContractService:
    return ContractService(db)

@router.post(
    "/",
    response_model=ContractOut,
    status_code=status.HTTP_201_CREATED,
    summary="M7.1 產生標準化合約"
)
async def api_create_contract(
    contract_data: ContractCreate,
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 接受提案後，建立合約草案。
    
    以前端傳入的 `proposal_id` 為基礎，自動產生一份
    狀態為「協商中」的合約。
    """
    # Service 層會驗證 current_user 是否為該提案的雇主
    return await service.create_contract_from_proposal(contract_data, current_user)

@router.get(
    "/my",
    response_model=List[ContractOut],
    summary="M7.2 獲取我的合約列表"
)
async def api_get_my_contracts(
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主 / 工作者) 獲取所有與我相關的合約列表 (包含我刊登的或我承接的)。
   
    """
    return await service.get_my_contracts(current_user)

@router.get(
    "/{contract_id}",
    response_model=ContractOut,
    summary="M7.2 檢視合約詳情"
)
async def api_get_contract_details(
    contract_id: str,
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主 / 工作者) 檢視單一合約的詳細內容。
    Service 層會驗證 current_user 必須是合約雙方之一。
    """
    return await service.get_contract_details(contract_id, current_user)

@router.put(
    "/{contract_id}",
    response_model=ContractOut,
    summary="M7.3 協商中修改合約 (雇主)"
)
async def api_update_draft_contract(
    contract_id: str,
    data: ContractUpdate,
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 在「協商中」狀態下，更新合約內容 (如金額、期限、範本內容)。
    這就是你提到的「自定義空間」。
    """
    return await service.update_draft_contract(contract_id, data, current_user)

@router.delete(
    "/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="M7.3 刪除/撤銷協商中合約 (雇主)"
)
async def api_delete_draft_contract(
    contract_id: str,
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 撤銷「協商中」的合約。
   
    """
    await service.delete_draft_contract(contract_id, current_user)
    return None # 204 No Content

@router.patch(
    "/{contract_id}/status",
    response_model=ContractOut,
    summary="M7.4/M7.5 合約狀態流轉 (雙方)"
)
async def api_update_contract_status(
    contract_id: str,
    data: ContractStatusUpdate,
    service: ContractService = Depends(get_contract_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主 / 工作者) 執行合約狀態變更。
    
    Service 層會使用狀態機驗證：
    - (工作者) 協商中 -> 已簽訂
    - (雇主) 驗收中 -> 已完成
    - (雇主) 驗收中 -> 進行中 (退回)
    - (雙方) ... -> 終止
    """
    return await service.update_contract_status(contract_id, data, current_user)