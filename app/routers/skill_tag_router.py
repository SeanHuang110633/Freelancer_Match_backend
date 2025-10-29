# app/routers/skill_tag_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.skill_tag_service import SkillTagService
from app.schemas.skill_tag_schema import SkillTagOut
from typing import List

router = APIRouter(
    prefix="/tags",
    tags=["Skills & Tags"],
    dependencies=[Depends(get_current_user)] # 必須登入才能看
)

@router.get("/", response_model=List[SkillTagOut])
async def get_all_skill_tags(db: AsyncSession = Depends(get_db)):
    """
    獲取所有可用的技能標籤 (供前端選擇器使用)
    """
    service = SkillTagService(db)
    return await service.get_all_tags()