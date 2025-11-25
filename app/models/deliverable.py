# app/models/deliverable.py

import uuid
from sqlalchemy import Column, String, TEXT, ForeignKey, TIMESTAMP, CHAR, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Deliverable(Base):
    __tablename__ = "deliverables"

    deliverable_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # 關聯欄位
    contract_id = Column(CHAR(36), ForeignKey("contracts.contract_id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id = Column(CHAR(36), ForeignKey("users.user_id"), nullable=False, index=True)
    
    # 內容
    description = Column(TEXT)
    file_url = Column(String(500))
    acceptance_status = Column(String(50), default='待驗收') # 狀態: 待驗收, 通過, 退回
    
    created_at = Column(TIMESTAMP, server_default=func.now())

    # --- Relationships ---
    
    # 關聯回合約
    contract = relationship("Contract", back_populates="deliverables")
    
    # 關聯回上傳者 (User)
    uploader = relationship("User")