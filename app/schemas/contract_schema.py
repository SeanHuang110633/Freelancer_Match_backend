# app/schemas/contract_schema.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# 複用其他模組的 Schema
from app.schemas.project_schema import ProjectOut
from app.schemas.user_schema import UserOut
from app.schemas.proposal_schema import UserOutWithProfile

# --- 1. 基礎欄位 ---
class ContractBase(BaseModel):
    title: str = Field(..., max_length=255)
    content: str
    amount: float = Field(..., gt=0)
    start_date: datetime
    end_date: datetime

# --- 2. (M7.1) 建立合約 (Input) ---
# 這是「接受提案」時，後端觸發 M7.1 所需的最小資訊
class ContractCreate(BaseModel):
    proposal_id: str

# --- 3. (M7.3) 雇主更新草案 (Input) ---
# 雇主在「協商中」狀態下可修改的欄位
class ContractUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

# --- 4. (M7.4, M7.5) 狀態更新 (Input) ---
# 用於「簽訂」、「標記進行中」、「提交驗收」、「完成」等操作
class ContractStatusUpdate(BaseModel):
    status: str # 後端 Service 會驗證狀態是否合法

# --- 5. 完整合約 (Output) ---
# 用於 GET /contracts/{id} 或 GET /contracts/my
class ContractOut(ContractBase):
    contract_id: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    # 巢狀載入關聯資料
    project: ProjectOut # 關聯的案件資訊
    
    # (注意) 這裡我們不只用 UserOut，
    # 對於 freelancer，我們使用 UserOutWithProfile
    # 對於 employer，我們使用 UserOut
    employer: UserOut 
    freelancer: UserOutWithProfile 

    class Config:
        from_attributes = True