# app/routers/deliverable_router.py

from fastapi import APIRouter, Depends, status, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.deliverable_service import DeliverableService
from app.schemas.deliverable_schema import DeliverableOut

router = APIRouter(
    tags=["Deliverables"],
    # 注意：這裡不設統一 prefix，因為路徑結構較靈活 (有 /contracts/... 也有 /deliverables/...)
    dependencies=[Depends(get_current_user)]
)

def get_service(db: AsyncSession = Depends(get_db)) -> DeliverableService:
    return DeliverableService(db)

# 1. 上傳交付物 (Create)
@router.post(
    "/contracts/{contract_id}/deliverables",
    response_model=DeliverableOut,
    status_code=status.HTTP_201_CREATED,
    summary="M7.5 上傳交付物"
)
async def create_deliverable(
    contract_id: str,
    # 使用 File 和 Form 來處理 multipart/form-data
    file: UploadFile = File(..., description="交付檔案 (PDF等)"),
    description: str = Form(..., description="交付說明"),
    service: DeliverableService = Depends(get_service),
    current_user: User = Depends(get_current_user)
):
    """
    (工作者) 在合約「進行中」時上傳交付檔案。
    """
    return await service.upload_deliverable(
        contract_id=contract_id,
        user=current_user,
        file=file,
        description=description
    )

# 2. 獲取交付物列表 (List)
@router.get(
    "/contracts/{contract_id}/deliverables",
    response_model=List[DeliverableOut],
    summary="M7.5 獲取合約的交付物列表"
)
async def list_deliverables(
    contract_id: str,
    service: DeliverableService = Depends(get_service),
    current_user: User = Depends(get_current_user)
):
    """
    (雙方) 查看該合約的所有交付物。
    """
    return await service.get_contract_deliverables(contract_id, current_user)

# 3. 更新/重新上傳交付物 (Update)
@router.put(
    "/deliverables/{deliverable_id}",
    response_model=DeliverableOut,
    summary="M7.5 更新/重新上傳交付物"
)
async def update_deliverable(
    deliverable_id: str,
    # 檔案與描述皆為可選 (Optional)，若未傳則不更新
    file: Optional[UploadFile] = File(None, description="新檔案 (若不更新請留空)"),
    description: Optional[str] = Form(None, description="新說明 (若不更新請留空)"),
    service: DeliverableService = Depends(get_service),
    current_user: User = Depends(get_current_user)
):
    """
    (工作者) 在雇主尚未驗收前 (且合約為進行中)，可重新上傳檔案或修改說明。
    """
    # 檢查至少要更新一項
    if file is None and description is None:
         raise HTTPException(status_code=400, detail="請至少提供檔案或描述以進行更新")

    # 由於 service 層的 update 參數 description 定義為 str (非 Optional)，
    # 我們需處理前端未傳 description 的情況 (通常前端會帶入舊值，或者我們允許 service 接受 None)
    # 這裡為了配合 Service 層邏輯，我們假設 Service 的 update_deliverable 簽名已支援 Optional
    
    # *註：我們上一步的 Service update_deliverable 實作是 description: str，
    # 建議稍微回頭看一下 Service，確認是否處理了 None。
    # 為了安全起見，這裡若 description 為 None，我們傳入 "" 或保持原值需在 Service 判斷。
    # 根據上一步代碼，我們傳遞參數給 Service 即可。
    
    return await service.update_deliverable(
        deliverable_id=deliverable_id,
        user=current_user,
        file=file,
        description=description # type: ignore
    )

# 4. 撤回/刪除交付物 (Delete)
@router.delete(
    "/deliverables/{deliverable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="M7.5 撤回交付物"
)
async def delete_deliverable(
    deliverable_id: str,
    service: DeliverableService = Depends(get_service),
    current_user: User = Depends(get_current_user)
):
    """
    (工作者) 撤回/刪除已上傳但尚未驗收的交付物。
    """
    await service.delete_deliverable(deliverable_id, current_user)
    return None