# app/models/employer_profile.py
from sqlalchemy import Column, String, TEXT, ForeignKey, JSON, CHAR
from app.core.database import Base

class EmployerProfile(Base):
    __tablename__ = "employer_profiles"
    profile_id = Column(CHAR(36), primary_key=True)
    user_id = Column(CHAR(36), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    company_name = Column(String(255))
    company_bio = Column(TEXT)
    company_logo_url = Column(String(500))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    social_links = Column(JSON)