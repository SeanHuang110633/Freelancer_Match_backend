# app/core/database.py

import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 定義連線參數
connect_args = {}

# 判斷是否需要 SSL (通常雲端資料庫需要)
# 這裡簡單判斷：如果連線字串不包含 localhost，或者是雲端環境，我們就啟用 SSL
# 更嚴謹的做法是在 settings 裡加一個 USE_SSL: bool = True
if "localhost" not in settings.DATABASE_URL and "127.0.0.1" not in settings.DATABASE_URL:
    # 建立 SSL Context
    #這會允許加密連線，但不強制驗證憑證 (相當於 ssl-mode=REQUIRED，但不驗證 CA)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # 將 SSL Context 傳入 asyncmy 的參數中
    connect_args["ssl"] = ssl_context

# 建立非同步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=True,
    # (重要) 透過 connect_args 傳遞驅動程式所需的特定參數
    connect_args=connect_args 
)

# 建立非同步 Session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db() -> AsyncSession:
    """FastAPI Dependency: 取得非同步資料庫 session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()