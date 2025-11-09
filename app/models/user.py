# models/user.py
from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.dialects.mysql import CHAR  # 針對 MySQL 的 UUID
from app.core.database import Base
import enum
from sqlalchemy.orm import relationship 

# 對應 SQL 中的 ENUM 型別
class UserRoleEnum(str, enum.Enum):
    freelancer = "自由工作者"
    employer = "雇主"
    admin = "系統管理員"

class User(Base):
    __tablename__ = "users"

    # 基本欄位
    user_id = Column(CHAR(36), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRoleEnum, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # 關聯設定  
    # (M4/M5)
    projects_owned = relationship(
        "Project", # <-- 使用字串
        back_populates="employer", 
        # foreign_keys="[Project.employer_id]"
    )

    # (M6)
    proposals = relationship(
        "Proposal", # <-- 使用字串
        back_populates="freelancer",
        # foreign_keys="[Proposal.freelancer_id]"
    )

    # (M2/M3)
    freelancer_profile = relationship(
        "FreelancerProfile", # <-- 使用字串
        back_populates="user", 
        uselist=False, 
        cascade="all, delete-orphan"
    )
    
    # (M2/M3)
    employer_profile = relationship(
        "EmployerProfile", # <-- 使用字串
        back_populates="user", 
        uselist=False, 
        cascade="all, delete-orphan"
    )

    # --- M7 (合約) 新增 ---
    # 作為雇主擁有的合約
    contracts_as_employer = relationship(
        "Contract",
        foreign_keys="[Contract.employer_id]",
        back_populates="employer"
    )
    
    # 作為工作者擁有的合約
    contracts_as_freelancer = relationship(
        "Contract",
        foreign_keys="[Contract.freelancer_id]",
        back_populates="freelancer"
    )