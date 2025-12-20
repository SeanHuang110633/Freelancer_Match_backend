# app/schemas/profile_schema.py

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Any, Optional
from app.schemas.skill_tag_schema import SkillTagOut

# --- 技能標籤 (用於 Profile 顯示) ---
class UserSkillTagOut(BaseModel):
    tag: SkillTagOut
    familiarity_level: int

    class Config:
        from_attributes = True

# --- 自由工作者 (Freelancer) ---
class FreelancerProfileBase(BaseModel):
    full_name: str | None = Field(None, max_length=100)
    bio: str | None = None
    phone: str | None = Field(None, max_length=50)
    # avatar_url: HttpUrl | None = Field(None, description="頭像 URL") 
    avatar_url: str | None = Field(None, description="頭像 URL") 
    social_links: dict | None = {} 

class FreelancerProfileCreate(FreelancerProfileBase):
    full_name: str = Field(..., max_length=100) 

class FreelancerProfileUpdate(FreelancerProfileBase):
    # pass 
    visibility: str | None = Field(None, enum=['公開', '僅受邀', '私人'])

class FreelancerProfileOut(FreelancerProfileBase):
    profile_id: str
    user_id: str
    reputation_score: float
    skills: List[UserSkillTagOut] = []
    visibility: str

    # (新增) 工作者四項指標平均分
    avg_communication: Optional[float] = None   # 溝通協調
    avg_professionalism: Optional[float] = None # 專業技術
    avg_punctuality: Optional[float] = None     # 準時交付
    avg_quality: Optional[float] = None         # 成果品質

    class Config:
        from_attributes = True

# (新增) 分頁回傳結構 - 搜尋結果用
class PaginatedFreelancerSearchOut(BaseModel):
    items: List[FreelancerProfileOut]
    total: int = Field(..., description="Total count")
    class Config:
        from_attributes = True

# 用於推薦列表的回傳格式
class FreelancerRecommendationOut(BaseModel):
    profile: FreelancerProfileOut # 巢狀包含完整的 Profile 資料
    recommendation_score: float = Field(..., description="推薦匹配分數")

    class Config:
        from_attributes = True 

class PaginatedFreelancerRecommendationOut(BaseModel):
    items: List[FreelancerRecommendationOut]
    total: int = Field(..., description="Total number of matched candidates")

    class Config:
        from_attributes = True

# --- 雇主 (Employer) ---
class EmployerProfileBase(BaseModel):
    company_name: str | None = Field(None, max_length=255)
    company_bio: str | None = None
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=50)
    # company_logo_url: HttpUrl | None = Field(None, description="公司 Logo URL") 
    company_logo_url: str | None = Field(None, description="公司 Logo URL") 
    social_links: dict | None = {}

class EmployerProfileCreate(EmployerProfileBase):
    company_name: str = Field(..., max_length=255) 

class EmployerProfileUpdate(EmployerProfileBase):
    pass 

class EmployerProfileOut(EmployerProfileBase):
    profile_id: str
    user_id: str
    
    # (新增) 雇主四項指標平均分 (預留給未來雇主詳情頁使用)
    avg_communication: Optional[float] = None # 溝通協調
    avg_quality: Optional[float] = None       # 需求品質
    avg_compensation: Optional[float] = None  # 福利報酬
    avg_process: Optional[float] = None       # 履約過程

    class Config:
        from_attributes = True

# --- (重要) 技能更新專用 Schema ---
class UserSkillsUpdate(BaseModel):
    # 前端傳回 tag_id 的列表
    skill_tag_ids: List[str]