# app/models/skill_tag.py
from sqlalchemy import Column, String, Boolean, ForeignKey, INT, CHAR
from sqlalchemy.orm import relationship
from app.core.database import Base

class SkillTag(Base):
    __tablename__ = "skill_tags"
    tag_id = Column(CHAR(36), primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(100))
    is_managed = Column(Boolean, default=True)

    # (正確) 關聯到 UserSkillTag (多)
    profiles = relationship("UserSkillTag", back_populates="tag")
    
    # (正確) 關聯到 ProjectSkillTag (多)
    projects = relationship("ProjectSkillTag", back_populates="tag")

class UserSkillTag(Base):
    __tablename__ = "user_skill_tags"
    user_skill_tag_id = Column(CHAR(36), primary_key=True)
    
    # --- 修正：加上 index=True ---
    profile_id = Column(CHAR(36), ForeignKey("freelancer_profiles.profile_id", ondelete="CASCADE"), index=True)
    tag_id = Column(CHAR(36), ForeignKey("skill_tags.tag_id", ondelete="RESTRICT"), index=True)
    
    familiarity_level = Column(INT, default=3)
    
    # (正確) 關聯回 SkillTag (一)
    tag = relationship("SkillTag", back_populates="profiles", lazy="selectin")
    
    # --- 修正：將 'profile' 關聯移入此 C (class) ---
    # 關聯回 FreelancerProfile (一)
    # 呼應 freelancer_profile.py 中的 'skills'
    profile = relationship("FreelancerProfile", back_populates="skills")
    # --- 修正結束 ---