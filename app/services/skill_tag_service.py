# app/services/skill_tag_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.skill_tag_repo import SkillTagRepository

class SkillTagService:
    def __init__(self, db: AsyncSession):
        self.repo = SkillTagRepository(db)

    async def get_all_tags(self):
        return await self.repo.list_all_tags()