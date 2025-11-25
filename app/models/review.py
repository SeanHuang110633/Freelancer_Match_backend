# app/models/review.py

import uuid
from sqlalchemy import Column, String, TEXT, DECIMAL, ForeignKey, TIMESTAMP, CHAR, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Review(Base):
    __tablename__ = "reviews"

    review_id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # 關聯鍵
    contract_id = Column(CHAR(36), ForeignKey("contracts.contract_id", ondelete="RESTRICT"), nullable=False, index=True)
    reviewer_id = Column(CHAR(36), ForeignKey("users.user_id"), nullable=False, index=True)
    reviewee_id = Column(CHAR(36), ForeignKey("users.user_id"), nullable=False, index=True)
    
    # --- 評分欄位 (1.0 - 5.0) ---
    
    # A. 雇主 評 工作者 (_fw = For Worker)
    rating_communication_fw = Column(DECIMAL(2, 1), nullable=True) # 溝通協調
    rating_professionalism_fw = Column(DECIMAL(2, 1), nullable=True) # 專業技術
    rating_punctuality_fw = Column(DECIMAL(2, 1), nullable=True) # 準時交付
    rating_quality_fw = Column(DECIMAL(2, 1), nullable=True) # 成果品質

    # B. 工作者 評 雇主 (_we = For Employer)
    rating_communication_we = Column(DECIMAL(2, 1), nullable=True) # 溝通協調
    rating_quality_we = Column(DECIMAL(2, 1), nullable=True) # 需求品質 (明確度)
    rating_compensation_we = Column(DECIMAL(2, 1), nullable=True) # 福利報酬 (合理性)
    rating_process_we = Column(DECIMAL(2, 1), nullable=True) # 履約過程 (順暢度)
    
    comment = Column(TEXT, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # --- Relationships ---
    contract = relationship("Contract", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    reviewee = relationship("User", foreign_keys=[reviewee_id])