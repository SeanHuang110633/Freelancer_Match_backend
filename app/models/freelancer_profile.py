# app/models/freelancer_profile.py
from sqlalchemy import Column, String, TEXT, ForeignKey, JSON, DECIMAL, CHAR, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.skill_tag import UserSkillTag

class FreelancerProfile(Base):
    __tablename__ = "freelancer_profiles"
    profile_id = Column(CHAR(36), primary_key=True)
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name = Column(String(100))
    bio = Column(TEXT)
    phone = Column(String(50))
    avatar_url = Column(String(500))
    visibility = Column(Enum('公開', '僅受邀', '私人'), default='公開')
    social_links = Column(JSON)
    reputation_score = Column(DECIMAL(3, 2), default=5.0)

    # (重要) 建立與 UserSkillTag 的 '多' 關聯
    # 'skills' 是我們在 Python 中用的名字
    # cascade="all, delete-orphan" 確保刪除 Profile 時，關聯的 skill tag 也一併刪除
    # lazy="selectin" 確保查詢 Profile 時會自動 (有效率地) 載入技能
    skills = relationship(
        "UserSkillTag", 
        back_populates="profile", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )

# (重要) 在 UserSkillTag 中補上反向關聯
UserSkillTag.profile = relationship("FreelancerProfile", back_populates="skills")