# app/repositories/user_repo.py
# 負責與使用者相關的資料庫操作
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        """
        透過 email 查詢使用者
        """
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    async def create_user(self, user: User) -> User:
        """
        新增使用者到資料庫
        """
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def get_user_by_id(self, user_id: str) -> User | None:
        """
        透過 user_id 查詢使用者
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()