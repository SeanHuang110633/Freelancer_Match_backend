# app/core/security.py
# 負責密碼雜湊與 JWT 權杖的產生與驗證
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.core.config import settings
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.user_schema import TokenData # 確保已匯入
from app.repositories.user_repo import UserRepository
from app.models.user import User

# 1. 密碼雜湊設定 (Bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 2. (重要) 定義 Token 從哪裡來 (Authorization Header)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證明文密碼是否與雜湊值相符"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """產生密碼的雜湊值"""
    return pwd_context.hash(password)

# 2. JWT 權杖產生與驗證
def create_access_token(data: dict) -> str:
    """
    根據傳入的 data (e.g., user_id) 產生 JWT access token
    """
    to_encode = data.copy() # 避免修改原始資料
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt



# (我們在第三步中暫時還用不到驗證 token，但先放在這裡)
def verify_access_token(token: str) -> dict | None:
    """驗證 JWT，回傳 payload 或 None"""
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> TokenData | None:
    """
    驗證 JWT，回傳 TokenData (Pydantic Model) 或 None
    """
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )

        # 從 payload 中解析 user_id 和 role
        user_id = payload.get("user_id")
        role = payload.get("role")

        if user_id is None or role is None:
            return None

        return TokenData(user_id=user_id, role=role)

    except JWTError:
        return None

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI 依賴項：驗證 Token 並回傳 User Model
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_access_token(token)
    if token_data is None:
        raise credentials_exception

    # (我們在 Token 中存了 user_id，改用 user_id 查詢)
    # (你需要先在 UserRepository 中新增 get_user_by_id)
    user_repo = UserRepository(db)

    # (我們去 user_repo.py 補上 get_user_by_id)
    user = await user_repo.get_user_by_id(user_id=token_data.user_id) 

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=400, detail="此帳號已被停權")

    return user