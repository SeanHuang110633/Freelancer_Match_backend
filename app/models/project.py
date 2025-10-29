from sqlalchemy import Column, String, TEXT, INT, DECIMAL, TIMESTAMP, ForeignKey, Enum, CHAR, func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.skill_tag import SkillTag # 稍後我們會修改 SkillTag

class Project(Base):
    __tablename__ = "projects"

    # 根據 DDL
    project_id = Column(CHAR(36), primary_key=True)
    employer_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(TEXT, nullable=False)
    status = Column(Enum('招募中', '已關閉', '已成案'), default='招募中')
    work_type = Column(Enum('遠端', '實體', '混合'), default='遠端')
    location = Column(String(255))
    budget_min = Column(DECIMAL(10, 2))
    budget_max = Column(DECIMAL(10, 2))
    proposals_deadline = Column(TIMESTAMP, nullable=True)
    completion_deadline = Column(TIMESTAMP, nullable=True)
    required_people = Column(INT, default=1)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # (重要) 建立與 'ProjectSkillTag' (關聯表) 的 '多' 關聯
    # 'skills' 是我們在 Python 中用的名字
    # lazy="selectin" 確保查詢 Project 時，會自動透過 JOIN 載入關聯的 skills
    skills = relationship(
        "ProjectSkillTag",
        back_populates="project",
        cascade="all, delete-orphan", # 刪除 Project 時，一併刪除關聯表中的紀錄
        lazy="selectin"
    )

class ProjectSkillTag(Base):
    __tablename__ = "project_skill_tags"

    # 根據 DDL
    project_skill_tag_id = Column(CHAR(36), primary_key=True)
    project_id = Column(CHAR(36), ForeignKey("projects.project_id", ondelete="CASCADE"))
    tag_id = Column(CHAR(36), ForeignKey("skill_tags.tag_id", ondelete="RESTRICT"))

    # 建立反向關聯回 Project
    project = relationship("Project", back_populates="skills")
    
    # (重要) 建立與 SkillTag (主表) 的 '一' 關聯
    # 這樣我們就可以透過 project.skills[0].tag 訪問到 SkillTag 的 name
    tag = relationship(
        "SkillTag", 
        back_populates="projects", # 這個 'projects' 屬性我們下一步會加到 SkillTag 上
        lazy="selectin"
    )