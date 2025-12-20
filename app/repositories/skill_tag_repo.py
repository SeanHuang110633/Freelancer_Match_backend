# app/repositories/skill_tag_repo.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models.skill_tag import SkillTag
from app.schemas.skill_tag_schema import SkillTagOut
from typing import List
from pydantic import TypeAdapter # (新增快取功能)
from app.core.cache import cached # (新增快取功能)

class SkillTagRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 套用快取：Key 前綴 "tags:all"，過期時間 1 天 (86400秒)
    # 回傳型別：List[SkillTagOut]
    @cached(key_prefix="tags:all", expire=86400, model=TypeAdapter(List[SkillTagOut]))
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