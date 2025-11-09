# app/models/employer_profile.py
from sqlalchemy import Column, String, TEXT, ForeignKey, JSON, CHAR
from sqlalchemy.orm import relationship # --- 修正：匯入 relationship ---
from app.core.database import Base

class EmployerProfile(Base):
    __tablename__ = "employer_profiles"
    profile_id = Column(CHAR(36), primary_key=True)
    # --- 修正：加上 index=True ---
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    company_name = Column(String(255))
    company_bio = Column(TEXT)
    company_logo_url = Column(String(500))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    social_links = Column(JSON)

    # --- (M2/M3 關鍵修復) 1-to-1 反向關聯到 User ---
    # 呼應 user.py 中的 'employer_profile'
    user = relationship("User", back_populates="employer_profile")
    # --- M2/M3 修復結束 ---