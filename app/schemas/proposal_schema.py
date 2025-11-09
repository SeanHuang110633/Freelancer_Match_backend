# app/schemas/proposal_schema.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# 匯入我們在 M1-M5 已經定義好的 UserOut 或 Profile Schema
# 這裡假設我們有一個精簡的 Schema 用於顯示提案者資訊
from app.schemas.profile_schema import FreelancerProfileOut 

# --- 基礎模型 ---
class ProposalBase(BaseModel):
    brief_description: Optional[str] = None

# --- 建立 (Create) ---
class ProposalCreate(ProposalBase):
    # 建立時，只需要 'brief_description'
    # project_id 和 freelancer_id 將從 URL 和 Token 中取得
    # attachment_url 將由 Service 層處理檔案後填入
    brief_description: str # 提案簡述設為必填

# --- 讀取 (Read / Out) ---
class ProposalOut(ProposalBase):
    model_config = ConfigDict(from_attributes=True) # orm_mode = True

    proposal_id: str
    project_id: str
    freelancer_id: str
    attachment_url: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


# 這個 Schema 用來代表 'freelancer' (User 物件) 以及他巢狀的 Profile
class UserOutWithProfile(BaseModel):
    """
    一個精簡的 Schema，用於在提案中顯示工作者資訊
    它會讀取 User model 上的欄位
    """
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    # (重要) 
    # 這裡的欄位 'freelancer_profile'
    # 必須對應到 'models/user.py' 中
    # User Model 上的 'freelancer_profile' relationship
    freelancer_profile: Optional[FreelancerProfileOut] = None

# --- 包含關聯資料的完整輸出 (供雇主檢視列表用) ---
class ProposalOutWithFreelancer(ProposalOut):
    # 嵌套顯示提案者的 Profile 資訊
    freelancer: Optional[UserOutWithProfile] = None