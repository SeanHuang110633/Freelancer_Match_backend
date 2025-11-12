# app/routers/proposal_router.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.proposal_service import ProposalService
from app.schemas.proposal_schema import (
    ProposalCreate, 
    ProposalOut, 
    ProposalOutWithFreelancer, # --- (新增) --- 確保匯入巢狀 Schema
    ProposalOutWithProject,
    ProposalOutWithFullProject
)
from app.schemas.project_schema import ProjectWithProposalsOut # 匯入新的 Schema
from pydantic import BaseModel # 用於定義狀態更新的請求 body

# 建立 API Router
router = APIRouter(
    prefix="/proposals",
    tags=["Proposals"],
    dependencies=[Depends(get_current_user)] # 重要：此 router 下所有 API 都需要登入
)

# -----------------------------------------------------------------
# 1. (工作者) 提交提案 (Use Case 6.1)
# -----------------------------------------------------------------
# 注意：我們將此 API 掛載在 /projects/ router 下，語意更清晰
# 我們需要一個單獨的 router 來處理這個
project_proposal_router = APIRouter(
    prefix="/projects",
    tags=["Proposals"], # 歸類到同一個 Tag
    dependencies=[Depends(get_current_user)]
)

@project_proposal_router.post(
    "/{project_id}/proposals", 
    response_model=ProposalOut, 
    status_code=status.HTTP_201_CREATED
)
async def submit_proposal(
    project_id: str,
    # (重要) 由於是檔案上傳，brief_description 必須來自 Form
    brief_description: str = Form(...),
    # 附件是可選的
    attachment: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    自由工作者對特定案件提交提案 (Use Case 6.1)。
    
    - 必須傳送 form-data。
    - 附件 (attachment) 必須是 PDF。
    """
    service = ProposalService(db)
    
    # 1. 將 Form data 轉為 Pydantic Schema
    proposal_data = ProposalCreate(brief_description=brief_description)
    
    # 2. 呼叫 Service
    try:
        new_proposal = await service.create_proposal(
            project_id=project_id,
            freelancer=current_user,
            proposal_data=proposal_data,
            attachment=attachment
        )
        return new_proposal
    except HTTPException as e:
        raise e
    except Exception as e:
        # 捕捉未預期的錯誤
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# -----------------------------------------------------------------
# --- (新增) ---
# 2. (雇主) 檢視特定案件的所有提案 (Use Case 6.3)
# -----------------------------------------------------------------
@project_proposal_router.get(
    "/{project_id}/proposals", 
    response_model=ProjectWithProposalsOut # --- (修改) --- 使用優化的 Schema
)
async def get_project_with_proposals(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    (雇主) 檢視自己刊登的特定案件 (詳情) 及其所收到的所有提案 (Use Case 6.3)。
    (對應 api/proposal.js 中的 getProposalsForProject)
    """
    service = ProposalService(db)
    try:
        project_with_proposals = await service.get_project_with_proposals(
            project_id, 
            current_user
        )
        return project_with_proposals
    except HTTPException as e:
        raise e
    except Exception as e:
        # 捕捉未預期的錯誤
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# -----------------------------------------------------------------
# 3. (工作者) 撤回提案 (Use Case 6.2)
# -----------------------------------------------------------------
@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    自由工作者撤回自己「已提交」的提案 (Use Case 6.2)。
    """
    service = ProposalService(db)
    try:
        await service.delete_proposal(proposal_id, current_user)
        return # 成功刪除，回傳 204
    except HTTPException as e:
        raise e
    

# -----------------------------------------------------------------
# 4. (工作者) 檢視自己提交的所有提案
# -----------------------------------------------------------------
@router.get("/my", response_model=List[ProposalOutWithProject])
async def get_my_proposals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    自由工作者檢視自己提交過的所有提案列表。
    (TODO: 可優化 Schema 來回傳關聯的 Project 資訊)
    """
    service = ProposalService(db)
    # Service 層已檢查 role，這裡直接傳入 user 即可
    if current_user.role != "自由工作者":
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有自由工作者可以檢視『我的提案』")
         
    proposals = await service.proposal_repo.get_proposals_by_freelancer_id(current_user.user_id)
    return proposals

# -----------------------------------------------------------------
# 5. (雇主) 選擇/拒絕人選 (Use Case 6.3, 6.5)
# -----------------------------------------------------------------

class ProposalStatusUpdate(BaseModel):
    """用於更新提案狀態的請求 Body"""
    status: str # 必須是 "已接受" 或 "已拒絕"

@router.patch("/{proposal_id}/status", response_model=ProposalOut)
async def update_proposal_status(
    proposal_id: str,
    update_data: ProposalStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    雇主接受 (選擇人選) 或拒絕一個提案 (Use Case 6.3, 6.5)。
    
    - status 欄位應傳入 "已接受" 或 "已拒絕"。
    - 接受提案 (M6) 會觸發後續動作 (M7 合約, M8 通知)。
    """
    service = ProposalService(db)
    try:
        updated_proposal = await service.update_proposal_status(
            proposal_id, 
            update_data.status, 
            current_user
        )
        return updated_proposal
    except HTTPException as e:
        raise e

# (新增) 需求三：獲取提案詳情
@router.get(
    "/{proposal_id}", 
    response_model=ProposalOutWithFullProject,
    summary="獲取提案詳情 (三欄式佈局)"
)
async def api_get_proposal_details(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    (工作者) 獲取自己單一提案的詳細資料。
    (用於三欄式檢視/編輯頁面)
    """
    service = ProposalService(db)
    return await service.get_proposal_details(proposal_id, current_user)

# (新增) 需求三：更新提案
@router.put(
    "/{proposal_id}", 
    response_model=ProposalOut,
    summary="更新提案內容 (Form-Data)"
)
async def api_update_proposal(
    proposal_id: str,
    brief_description: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    (工作者) 更新「已提交」的提案內容。
    - 必須傳送 form-data。
    - 附件 (attachment) 必須是 PDF。
    """
    service = ProposalService(db)
    return await service.update_proposal(
        proposal_id=proposal_id,
        user=current_user,
        brief_description=brief_description,
        attachment=attachment
    )