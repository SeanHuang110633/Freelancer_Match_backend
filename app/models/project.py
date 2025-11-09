# models/project.py
from sqlalchemy import Column, String, TEXT, INT, DECIMAL, TIMESTAMP, ForeignKey, Enum, CHAR, func
from sqlalchemy.orm import relationship
from app.core.database import Base
# (移除) from app.models.skill_tag import SkillTag # --- 修正：移除頂層 import，避免循環依賴 ---

class Project(Base):
    # 告訴 SQLAlchemy，這個類別對應到資料庫中名為 projects 的表格 (table)
    __tablename__ = "projects"

    # 根據 DDL
    project_id = Column(CHAR(36), primary_key=True)
    # --- 修正：加上 index=True 提升 FK 查詢效能 ---
    employer_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True) 
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
    
    # --- (M4/M5 補全) 建立與 User (雇主) 的 '一' 關聯 ---
    # 呼應 user.py 中的 'projects_owned'
    employer = relationship(
        "User", 
        back_populates="projects_owned"
    )
    # --- M4/M5 結束 ---

    # (M4/M5) 建立與 'ProjectSkillTag' (關聯表) 的 '多' 關聯
    skills = relationship(
        "ProjectSkillTag",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # --- M6 (提案模組) 新增 ---
    # 建立與 Proposal (提案表) 的 '多' 關聯
    # 呼應 proposal.py 中 'project'
    proposals = relationship(
        "Proposal", 
        back_populates="project",
        cascade="all, delete-orphan" # 刪除案件時，一併刪除關聯提案
    )
    
    # --- M7 (合約) 新增 ---
    # 關聯到此案件下所有的合約 (理論上只會有一個，但架構允許多個)
    contracts = relationship(
        "Contract",
        back_populates="project"
    )

    # 新增 M8 (聊天室) 的反向關聯
    # 告訴 Project model，'ChatRoom' model 會透過 'project' 屬性關聯回來
    chat_rooms = relationship(
        "ChatRoom",
        back_populates="project",
        # 明確指定 ChatRoom 上的外鍵
        foreign_keys="[ChatRoom.context_project_id]" 
    )
    # --- (修正結束) ---

class ProjectSkillTag(Base):
    __tablename__ = "project_skill_tags"

    # 根據 DDL
    project_skill_tag_id = Column(CHAR(36), primary_key=True)
    # --- 修正：加上 index=True 提升 FK 查詢效能 ---
    project_id = Column(CHAR(36), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True)
    tag_id = Column(CHAR(36), ForeignKey("skill_tags.tag_id", ondelete="RESTRICT"), index=True)

    # 建立反向關聯回 Project
    project = relationship("Project", back_populates="skills")
    
    # (重要) 建立與 SkillTag (主表) 的 '一' 關聯
    # "SkillTag" 已使用字串，是正確的
    tag = relationship(
        "SkillTag", 
        back_populates="projects", 
        lazy="selectin"
    )