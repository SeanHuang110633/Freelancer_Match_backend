# app/schemas/project_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.schemas.proposal_schema import ProposalOutWithFreelancer, ProposalOutWithFullProject
from app.schemas.skill_tag_schema import SkillTagOut 
from app.schemas.user_schema import UserOutWithEmployerProfile

# 1. 用於在 ProjectOut 中顯示巢狀的技能標籤
class ProjectSkillTagOut(BaseModel):
    tag: SkillTagOut
    class Config:
        from_attributes = True 

# 2. 基礎欄位 (對應 Model)
class ProjectBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: str
    location: Optional[str] = Field(None, max_length=255)
    work_type: str = Field("遠端", enum=['遠端', '實體', '混合'])
    budget_min: Optional[float] = Field(None, gt=0)
    budget_max: Optional[float] = Field(None, gt=0)
    proposals_deadline: Optional[datetime] = None
    completion_deadline: Optional[datetime] = None
    required_people: int = Field(1, gt=0)

# 3. 雇主刊登案件時的 Request Body (Input)
class ProjectCreate(ProjectBase):
    skill_tag_ids: List[str] = []

# 4. 雇主更新案件時的 Request Body (Input)
class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)
    work_type: Optional[str] = Field(None, enum=['遠端', '實體', '混合'])
    budget_min: Optional[float] = Field(None, gt=0)
    budget_max: Optional[float] = Field(None, gt=0)
    proposals_deadline: Optional[datetime] = None
    completion_deadline: Optional[datetime] = None
    required_people: Optional[int] = Field(None, gt=0)
    skill_tag_ids: Optional[List[str]] = None
    status: Optional[str] = Field(None, enum=['招募中', '已關閉', '已成案'])

# 5. 回傳給前端的案件資料 (Output)
class ProjectOut(ProjectBase):
    project_id: str
    employer: UserOutWithEmployerProfile 
    status: str
    skills: List[ProjectSkillTagOut] = []

    class Config:
        from_attributes = True 

# (新增) 分頁的案件搜尋回應格式
class PaginatedProjectSearchOut(BaseModel):
    items: List[ProjectOut]
    total: int = Field(..., description="Total count")

    class Config:
        from_attributes = True

# 6. 推薦系統使用的回應格式
class ProjectRecommendationOut(BaseModel):
    project: ProjectOut 
    recommendation_score: float = Field(..., description="推薦匹配分數")

    class Config:
        from_attributes = True 

# 7. 分頁的推薦案件回應格式
class PaginatedProjectRecommendationOut(BaseModel):
    items: List[ProjectRecommendationOut]
    total: int = Field(..., description="Total number of matched candidates")

    class Config:
        from_attributes = True

# 8. 用於雇主管理案件的提案
class ProjectWithProposalsOut(ProjectOut):
    proposals: List[ProposalOutWithFreelancer] = []
    class Config:
        from_attributes = True

# (新增) 需求二：用於更新狀態的 Schema
class ProjectStatusUpdate(BaseModel):
    status: str = Field(..., enum=['招募中', '已關閉', '已成案'])

ProposalOutWithFullProject.model_rebuild()