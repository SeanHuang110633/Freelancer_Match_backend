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
   # (修改) 
   # 1. 補上反向關聯到 UserSkillTag (使用者 Profile)
   # 讓 SQLAlchemy 知道 SkillTag.profiles 對應 UserSkillTag.tag
   profiles = relationship("UserSkillTag", back_populates="tag")
    
   # (新增) 
   # 2. 補上反向關聯到 ProjectSkillTag (案件)
   # 讓 SQLAlchemy 知道 SkillTag.projects 對應 ProjectSkillTag.tag
   projects = relationship("ProjectSkillTag", back_populates="tag")

class UserSkillTag(Base):
   __tablename__ = "user_skill_tags"
   user_skill_tag_id = Column(CHAR(36), primary_key=True)
   profile_id = Column(CHAR(36), ForeignKey("freelancer_profiles.profile_id", ondelete="CASCADE"))
   tag_id = Column(CHAR(36), ForeignKey("skill_tags.tag_id", ondelete="RESTRICT"))
   familiarity_level = Column(INT, default=3)
   
   # (修改) 
   # 1. 將 'tag' 關聯改為雙向
   # lazy="selectin" 確保查詢 Profile.skills 時會自動載入 tag 的詳細資料
   tag = relationship("SkillTag", back_populates="profiles", lazy="selectin")
   
   # 'profile' 關聯由 app/models/freelancer_profile.py 建立