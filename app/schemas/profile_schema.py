# app/schemas/profile_schema.py
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Any
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
    avatar_url: HttpUrl | None = Field(None, description="頭像 URL")
    social_links: dict | None = {} # 接收 JSON/dict

class FreelancerProfileCreate(FreelancerProfileBase):
    full_name: str = Field(..., max_length=100) # 建立時姓名必填

class FreelancerProfileUpdate(FreelancerProfileBase):
    # pass # 更新時全為選填
    visibility: str | None = Field(None, enum=['公開', '僅受邀', '私人'])

class FreelancerProfileOut(FreelancerProfileBase):
    profile_id: str
    user_id: str
    reputation_score: float
    skills: List[UserSkillTagOut] = [] # (重要) 巢狀 Pydantic
    visibility: str
    class Config:
        from_attributes = True

# (新增) 用於推薦列表的回傳格式
class FreelancerRecommendationOut(BaseModel):
    profile: FreelancerProfileOut # 巢狀包含完整的 Profile 資料
    recommendation_score: float = Field(..., description="推薦匹配分數")

    class Config:
        from_attributes = True # 允許從非 dict 物件建立

# --- 雇主 (Employer) ---
class EmployerProfileBase(BaseModel):
    company_name: str | None = Field(None, max_length=255)
    company_bio: str | None = None
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=50)
    company_logo_url: HttpUrl | None = Field(None, description="公司 Logo URL")
    social_links: dict | None = {}

class EmployerProfileCreate(EmployerProfileBase):
    company_name: str = Field(..., max_length=255) # 建立時公司名必填

class EmployerProfileUpdate(EmployerProfileBase):
    pass # 更新時全為選填

class EmployerProfileOut(EmployerProfileBase):
    profile_id: str
    user_id: str
    
    class Config:
        from_attributes = True

# --- (重要) 技能更新專用 Schema ---
class UserSkillsUpdate(BaseModel):
    # 前端傳回 tag_id 的列表
    skill_tag_ids: List[str]