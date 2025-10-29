from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repo import UserRepository
from app.core.security import verify_password, create_access_token, get_password_hash
from app.models.user import User
from fastapi import HTTPException, status # (新增)
from app.schemas.user_schema import UserCreate # (新增)
import uuid # (新增)

class AuthService:
    def __init__(self, db: AsyncSession):
        self.user_repo = UserRepository(db)

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """
        驗證使用者帳號密碼。
        成功回傳 User 物件，失敗回傳 None。
        """
        user = await self.user_repo.get_user_by_email(email)
        
        # 1. 檢查使用者是否存在
        if not user:
            return None
        
        # 2. 檢查是否被停權
        if not user.is_active:
            return None
            
        # 3. 檢查密碼是否正確
        if not verify_password(plain_password=password, hashed_password=user.password_hash):
            return None
            
        return user
    

    # 2. 在 AuthService class 中加入 register_user 方法
    async def register_user(self, user_create: UserCreate) -> User:
        """
        處理使用者註冊
        """
        # 1. 檢查 Email 是否已被註冊
        existing_user = await self.user_repo.get_user_by_email(user_create.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此 Email 已經被註冊",
            )
            
        # 2. 雜湊密碼 (使用我們 security.py 中的函式)
        hashed_password = get_password_hash(user_create.password)
        
        # 3. 建立 User ORM 模型
        new_user = User(
            user_id=str(uuid.uuid4()), # 產生一個新的 UUID
            email=user_create.email,
            password_hash=hashed_password,
            role=user_create.role # 直接使用傳入的 Enum
        )
        
        # 4. 呼叫 Repository 儲存到資料庫
        created_user = await self.user_repo.create_user(new_user)
        return created_user


    def create_login_token(self, user: User) -> str:
        """
        為指定使用者建立 access token
        """
        access_token = create_access_token(
            data={
                "sub": user.email, # 'sub' 是 JWT 的標準欄位，通常存 user id
                "user_id": str(user.user_id),
                "role": user.role.value # 確保存入的是字串
            }
        )
        return access_token