# app/schemas/project_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.schemas.proposal_schema import ProposalOutWithFreelancer
from app.schemas.skill_tag_schema import SkillTagOut # 複用我們在 Step 4 建立的 Schema

# 1. 用於在 ProjectOut 中顯示巢狀的技能標籤
class ProjectSkillTagOut(BaseModel):
    tag: SkillTagOut
    # 案件需求標籤沒有 "熟悉度"

    class Config:
        from_attributes = True # 啟用 ORM 模式

# 2. 基礎欄位 (對應 Model)
class ProjectBase(BaseModel):
    # 欄位符合需求文件 和 DDL
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
    # (重要) 雇主在前端選擇的技能標籤 ID 列表
    skill_tag_ids: List[str] = []

# 4. 雇主更新案件時的 Request Body (Input)
# (所有欄位皆可選)
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
    employer_id: str
    status: str
    
    # (重要) 巢狀回傳完整的技能標籤資料
    skills: List[ProjectSkillTagOut] = []

    class Config:
        from_attributes = True # 啟用 ORM 模式

# 6. 推薦系統使用的回應格式
class ProjectRecommendationOut(BaseModel):
    project: ProjectOut # 巢狀包含完整的 Project 資料
    recommendation_score: float = Field(..., description="推薦匹配分數")

    class Config:
        from_attributes = True # 允許從非 dict 物件建立

# 7. 分頁的推薦案件回應格式
class PaginatedProjectRecommendationOut(BaseModel):
    items: List[ProjectRecommendationOut]
    total: int = Field(..., description="Total number of matched candidates")

    class Config:
        from_attributes = True


# 8. 用於雇主管理案件的提案，回傳案件詳情以及所有關聯的提案列表
class ProjectWithProposalsOut(ProjectOut):
    """
    用於雇主管理介面，回傳案件詳情以及所有關聯的提案列表
    """
    proposals: List[ProposalOutWithFreelancer] = []

    class Config:
        from_attributes = True