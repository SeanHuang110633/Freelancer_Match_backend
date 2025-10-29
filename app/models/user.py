from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.dialects.mysql import CHAR  # 針對 MySQL 的 UUID
from app.core.database import Base
import enum

# 對應 SQL 中的 ENUM 型別
class UserRoleEnum(str, enum.Enum):
    freelancer = "自由工作者"
    employer = "雇主"
    admin = "系統管理員"

class User(Base):
    __tablename__ = "users"

    user_id = Column(CHAR(36), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRoleEnum, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # (我們暫時不需要 created_at 和 updated_at)