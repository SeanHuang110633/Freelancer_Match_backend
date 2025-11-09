# app/models/proposal.py
import uuid
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import relationship
from app.core.database import Base
# --- 修正：移除頂層 Model 匯入，避免循環依賴 ---
# (移除) from app.models.project import Project
# (移除) from app.models.user import User
# --- 修正結束 ---

class Proposal(Base):
    __tablename__ = "proposals"

    proposal_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # ForeignKey 指向 "tablename.columnname"
    # index=True 對應我們剛剛的討論，是正確的效能優化
    project_id = Column(CHAR(36), ForeignKey("projects.project_id"), nullable=False, index=True)
    freelancer_id = Column(CHAR(36), ForeignKey("users.user_id"), nullable=False, index=True)
    
    brief_description = Column(Text)
    attachment_url = Column(String(500)) # 這就是我們儲存 URL 的欄位
    
    # 根據 DB Schema，我們也加入 status 和 timestamps
    status = Column(String(50), default='已提交') 
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # --- 建立關聯 (Relationships) ---
    
    # (正確) 關聯 C (class) 名稱使用字串 "Project"，呼應 project.py 中的 "proposals"
    project = relationship("Project", back_populates="proposals")
    
    # (正確) 關聯 C (class) 名稱使用字串 "User"，呼應 user.py 中的 "proposals"
    freelancer = relationship("User", back_populates="proposals")

    # --- M7 (合約) 新增 ---
    # 1-to-1 關聯到合約
    contract = relationship(
        "Contract",
        back_populates="proposal",
        uselist=False # 確保是 1-to-1
    )