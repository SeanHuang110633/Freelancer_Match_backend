import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 定義連線參數
connect_args = {}

# 【修正說明】
# 在 Docker 內部網路環境 (如 stress test)，透過 Service Name (db_system) 連線時，
# 預設不支援也不需要 SSL。強制開啟會導致 aiomysql 握手失敗 (SSLWantReadError)。
# 因此我們先註解掉這段自動判斷，強制走純文字連線。

# if "localhost" not in settings.DATABASE_URL and "127.0.0.1" not in settings.DATABASE_URL:
#     # 建立 SSL Context
#     # 這會允許加密連線，但不強制驗證憑證 (相當於 ssl-mode=REQUIRED，但不驗證 CA)
#     ssl_context = ssl.create_default_context()
#     ssl_context.check_hostname = False
#     ssl_context.verify_mode = ssl.CERT_NONE
#
#     # 將 SSL Context 傳入 asyncmy 的參數中
#     connect_args["ssl"] = ssl_context

# 建立非同步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False, # 壓測時建議關閉 echo，否則 log 會吃光 I/O
    connect_args=connect_args, # 這裡現在是空的 dict，確保乾淨連線

    # --- (新增) 套用設定 ---
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    
    # 【新增】回收時間設為 1800 秒 (30分鐘)，避免 MySQL 斷開閒置連線導致後端報錯
    pool_recycle=1800,
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