# app/repositories/skill_tag_repo.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models.skill_tag import SkillTag
from typing import List

class SkillTagRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all_tags(self) -> List[SkillTag]:
        """列出所有系統管理的技能標籤"""
        stmt = select(SkillTag).where(SkillTag.is_managed == True)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def count_tags_by_ids(self, tag_ids: List[str]) -> int:
        """
        計算傳入的 ID 列表中，有多少個是存在於資料庫的
        """
        if not tag_ids:
            return 0
            
        stmt = select(func.count(SkillTag.tag_id)).where(
            SkillTag.tag_id.in_(tag_ids)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first() or 0