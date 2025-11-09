# app/repositories/proposal_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional
import uuid

from app.models.proposal import Proposal
from app.models.user import User # 用於 joinedload

class ProposalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_proposal_by_id(self, proposal_id: str) -> Optional[Proposal]:
        """
        透過 ID 獲取單一提案
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_proposal_by_id_with_project(self, proposal_id: str) -> Optional[Proposal]:
        """
        透過 ID 獲取單一提案，並載入關聯的 Project (用於權限檢查)
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id).options(
            # 使用 joinedload 載入 project，因為我們需要 project.employer_id
            joinedload(Proposal.project) 
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # --- ( M7 修正：新增此函式 ) ---
    async def get_proposal_by_id_with_project_and_freelancer(
        self, proposal_id: str
    ) -> Optional[Proposal]:
        """
        (M7.1) 透過 ID 獲取提案，並 Eager Load 其 Project 和 Freelancer (User)
        
        這是 ContractService 建立合約時所需的函式，
        確保 proposal.project 和 proposal.freelancer 都有資料。
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id).options(
            # 1. 載入 Project (M6 檢查雇主 ID 需要)
            joinedload(Proposal.project),
            # 2. 載入 Freelancer (M7 建立合約需要)
            joinedload(Proposal.freelancer)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()
    # --- ( M7 修正結束 ) ---

    async def check_existing_proposal(self, project_id: str, freelancer_id: str) -> Optional[Proposal]:
        """
        檢查特定使用者是否已對特定案件提案 (用於 Use Case 6.1 的唯一性檢查)
        """
        stmt = select(Proposal).where(
            Proposal.project_id == project_id,
            Proposal.freelancer_id == freelancer_id
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_proposals_by_project_id(self, project_id: str) -> List[Proposal]:
        """
        獲取特定案件的所有提案 (雇主檢視用, Use Case 6.3)
        """
        stmt = select(Proposal).where(Proposal.project_id == project_id).options(
            # 效能優化：
            # 1. 載入提案者 (freelancer, 即 User C (class))
            # 2. 接著載入該 User 的 freelancer_profile
            # 這樣 Service 層回傳 Schema 時不會N+1查詢
            selectinload(Proposal.freelancer).selectinload(User.freelancer_profile)
        ).order_by(Proposal.created_at.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_proposals_by_freelancer_id(self, freelancer_id: str) -> List[Proposal]:
        """
        獲取特定工作者的所有提案 (工作者檢視「我的提案」用)
        """
        stmt = select(Proposal).where(Proposal.freelancer_id == freelancer_id).options(
            # 載入關聯的案件資訊
            selectinload(Proposal.project)
        ).order_by(Proposal.created_at.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create_proposal(self, proposal: Proposal) -> Proposal:
        """
        新增提案
        """
        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)
        return proposal

    async def update_proposal(self, proposal: Proposal) -> Proposal:
        """
        更新提案 (主要用於更新 status)
        """
        await self.db.commit()
        await self.db.refresh(proposal)
        return proposal

    async def delete_proposal(self, proposal: Proposal) -> None:
        """
        刪除提案 (撤回提案, Use Case 6.2)
        """
        await self.db.delete(proposal)
        await self.db.commit()
        return