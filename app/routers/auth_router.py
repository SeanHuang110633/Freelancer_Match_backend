import logging # (新增)
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.auth_service import AuthService
from app.schemas.user_schema import Token, UserCreate, UserOut


logger = logging.getLogger(__name__) # (新增) 取得 logger

router = APIRouter(
    prefix="/auth", # 路由前綴
    tags=["Auth"]    # API 文件分類標籤
)


# 2. (新增) 註冊 API 端點
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_new_user(
    user_data: UserCreate, # Request Body 會被 Pydantic 驗證
    db: AsyncSession = Depends(get_db)
):
    """
    註冊新使用者 (自由工作者 / 雇主)
    
    - 密碼需至少8碼，且包含英文和數字。
    """
    auth_service = AuthService(db)
    
    # 服務層中的 HTTPException 會自動被 FastAPI 捕捉並回傳
    new_user = await auth_service.register_user(user_data)
    
    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    # (重要) 使用 OAuth2PasswordRequestForm 會強制 API 只接受 form-data
    # 格式為 username=...&password=...
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    提供帳號 (username 欄位傳 email) 和密碼以取得 Access Token
    """
    auth_service = AuthService(db)
    
    # form_data.username 欄位就是我們的 email
    user = await auth_service.authenticate_user(
        email=form_data.username, 
        password=form_data.password
    )

    logger.info(f"User logged in: {user.user_id}")    
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正確的帳號或密碼",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = auth_service.create_login_token(user)
    
    return {"access_token": access_token, "token_type": "bearer"}