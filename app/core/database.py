from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 建立非同步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True, # 每次從連線池取連線前，先 PING 一次，確保連線有效
    echo=True, # (可選) 設為 True 會在 console 印出 SQL 語句
)

# 建立非同步 Session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 建立 ORM Model 基底類別
Base = declarative_base()

# (重要) 取得 DB Session 的 Dependency
async def get_db() -> AsyncSession:
    """FastAPI Dependency: 取得非同步資料庫 session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()