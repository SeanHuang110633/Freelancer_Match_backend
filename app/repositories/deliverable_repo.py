# app/repositories/deliverable_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional # (新增)
from app.models.deliverable import Deliverable

class DeliverableRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_deliverable(self, deliverable: Deliverable) -> Deliverable:
        """
        (C) 新增交付物紀錄
        """
        self.db.add(deliverable)
        await self.db.commit()
        await self.db.refresh(deliverable)
        return deliverable

    async def list_deliverables_by_contract_id(self, contract_id: str) -> List[Deliverable]:
        """
        (R) 獲取特定合約的所有交付物 (依建立時間倒序排列)
        """
        stmt = (
            select(Deliverable)
            .where(Deliverable.contract_id == contract_id)
            .order_by(Deliverable.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # --- (新增) 修改與刪除所需的方法 ---

    async def get_deliverable_by_id(self, deliverable_id: str) -> Optional[Deliverable]:
        """
        (R) 依 ID 獲取單一交付物
        """
        stmt = select(Deliverable).where(Deliverable.deliverable_id == deliverable_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def update_deliverable(self, deliverable: Deliverable) -> Deliverable:
        """
        (U) 更新交付物紀錄
        """
        await self.db.commit()
        await self.db.refresh(deliverable)
        return deliverable

    async def delete_deliverable(self, deliverable: Deliverable) -> None:
        """
        (D) 刪除交付物紀錄
        """
        await self.db.delete(deliverable)
        await self.db.commit()