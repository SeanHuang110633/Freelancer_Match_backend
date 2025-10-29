# app/schemas/skill_tag_schema.py
from pydantic import BaseModel

class SkillTagOut(BaseModel):
    tag_id: str
    name: str
    category: str | None

    class Config:
        from_attributes = True