# app/models/freelancer_profile.py
from sqlalchemy import Column, String, TEXT, ForeignKey, JSON, DECIMAL, CHAR, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base

class FreelancerProfile(Base):
    __tablename__ = "freelancer_profiles"
    profile_id = Column(CHAR(36), primary_key=True)
    # --- 修正：加上 index=True ---
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    full_name = Column(String(100))
    bio = Column(TEXT)
    phone = Column(String(50))
    avatar_url = Column(String(500))
    visibility = Column(Enum('公開', '僅受邀', '私人'), default='公開')
    social_links = Column(JSON)
    reputation_score = Column(DECIMAL(3, 2), default=5.0)

    # --- (M2/M3 關鍵修復) 1-to-1 反向關聯到 User ---
    # 呼應 user.py 中的 'freelancer_profile'
    user = relationship("User", back_populates="freelancer_profile")
    # --- M2/M3 修復結束 ---

    # (正確) 建立與 UserSkillTag 的 '多' 關聯
    skills = relationship(
        "UserSkillTag", 
        back_populates="profile", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
