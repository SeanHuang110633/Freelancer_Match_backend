# app/models/contract.py

import uuid
from sqlalchemy import (
    Column, String, TEXT, DECIMAL, TIMESTAMP, INT, ForeignKey, Enum, CHAR, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base

# --- ( M7 狀態機重構 ) ---
ContractStatusEnum = Enum(
    '協商中', '進行中', 
    '雇主請求修改', '工作者請求修改', 
    '雇主請求終止', '工作者請求終止', 
    '工作者要求驗收', '已完成', '終止',
    name="contract_status_enum"
)
# --- ( M7 修正結束 ) ---

class Contract(Base):
    __tablename__ = "contracts"

    contract_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # --- 關聯 ---
    project_id = Column(CHAR(36), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False, index=True)
    proposal_id = Column(CHAR(36), ForeignKey("proposals.proposal_id", ondelete="RESTRICT"), unique=True, nullable=False, index=True)
    employer_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True)
    freelancer_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True)
    
    # --- 合約內容 ---
    title = Column(String(255), nullable=False)
    content = Column(TEXT, nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    start_date = Column(TIMESTAMP, nullable=False, server_default=func.now())
    end_date = Column(TIMESTAMP, nullable=False)
    
    # --- 狀態管理 ---
    status = Column(ContractStatusEnum, default='協商中', nullable=False)
    version = Column(INT, default=1)
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # --- SQLAlchemy Relationships (反向關聯) ---

    # 1-to-1 關聯回 Proposal
    proposal = relationship(
        "Proposal", 
        back_populates="contract"
    )
    
    # 1-to-Many 關聯回 Project
    project = relationship(
        "Project", 
        back_populates="contracts"
    )

    # 關聯回 User (雇主)
    employer = relationship(
        "User", 
        foreign_keys=[employer_id], 
        back_populates="contracts_as_employer"
    )
    
    # 關聯回 User (工作者)
    freelancer = relationship(
        "User", 
        foreign_keys=[freelancer_id], 
        back_populates="contracts_as_freelancer"
    )

    # (新增) 1-to-Many 關聯到 Deliverable
    deliverables = relationship(
        "Deliverable",
        back_populates="contract",
        cascade="all, delete-orphan", # 刪除合約時，連同交付物記錄一起刪除
        lazy="selectin" # 列表查詢時自動載入，避免 N+1
    )

    # (新增) 1-to-Many 關聯到 Review
    # 一個合約最多會有 2 筆評價 (雙方互評)
    reviews = relationship(
        "Review",
        back_populates="contract",
        cascade="all, delete-orphan", # 刪除合約時評價一併刪除
        lazy="selectin" # 列表查詢時自動載入
    )