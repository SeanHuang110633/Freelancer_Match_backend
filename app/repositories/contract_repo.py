# app/repositories/contract_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.sql.expression import or_, exists
from typing import List, Optional

# 匯入 M7 Model
from app.models.contract import Contract

# 匯入 M7 Eager Loading 所需的所有關聯 Model
from app.models.project import Project
from app.models.proposal import Proposal
from app.models.user import User
from app.models.freelancer_profile import FreelancerProfile
from app.models.employer_profile import EmployerProfile
from app.models.skill_tag import UserSkillTag, SkillTag


class ContractRepository:
    """
    封裝對 'contracts' 資料表的 CRUD 操作
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_common_contract_options(self):
        """
        (效能關鍵) 
        定義 ContractOut Schema 所需的 Eager Loading 策略，避免 N+1 查詢
        """
        return [
            # 1. 載入案件資訊 (1-to-1)，
            #    並且必須巢狀載入 ProjectOut 所需的 'employer.employer_profile'
            joinedload(Contract.project).options(
                joinedload(Project.employer).
                selectinload(User.employer_profile)
            ),
            # (修改結束)
            
            # 2. 載入雇主 (User) 資訊 (1-to-1)
            joinedload(Contract.employer),
            
            # 3. 載入工作者 (User) 及其 Profile (巢狀)
            joinedload(Contract.freelancer)
                # 3a. User -> FreelancerProfile (1-to-1)
                .selectinload(User.freelancer_profile)
                # 3b. Profile -> Skills (1-to-Many)
                .selectinload(FreelancerProfile.skills)
                # 3c. Skills -> Tag (1-to-1)
                .joinedload(UserSkillTag.tag),
            
            # 4. 載入關聯的提案 (1-to-1)
            joinedload(Contract.proposal)
        ]

    async def create_contract(self, contract: Contract) -> Contract:
        """
        (C) 將新的合約物件存入資料庫
        """
        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        return contract

    async def check_contract_exists_by_proposal(self, proposal_id: str) -> bool:
        """
        (R) 檢查是否已有合約關聯到此 proposal_id (proposal_id 是 unique)
        """
        stmt = select(exists().where(Contract.proposal_id == proposal_id))
        result = await self.db.execute(stmt)
        return result.scalar()

    async def get_contract_by_id(self, contract_id: str) -> Optional[Contract]:
        """
        (R) 透過 ID 獲取單一合約，並 Eager Loading 關聯資料
        """
        stmt = select(Contract).where(Contract.contract_id == contract_id)
        
        # 套用 Eager Loading 策略
        stmt = stmt.options(*self._get_common_contract_options())
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_contracts_by_user(self, user_id: str) -> List[Contract]:
        """
        (R) 獲取某個使用者 (作為雇主 或 作為工作者) 的所有合約
        """
        stmt = select(Contract).where(
            or_(
                Contract.employer_id == user_id,
                Contract.freelancer_id == user_id
            )
        ).order_by(Contract.updated_at.desc())
        
        # 對列表查詢同樣套用 Eager Loading
        stmt = stmt.options(*self._get_common_contract_options())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_contract(self, contract: Contract) -> Contract:
        """
        (U) 儲存對現有 Contract 物件的變更
        (由 Service 層傳入修改後的 Contract 物件)
        """
        await self.db.commit()
        await self.db.refresh(contract)
        return contract

    async def delete_contract(self, contract: Contract) -> None:
        """
        (D) 從資料庫刪除一個合約
        (僅限 '協商中' 狀態)
        """
        await self.db.delete(contract)
        await self.db.commit()