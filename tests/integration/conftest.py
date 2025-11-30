# tests/integration/conftest.py

import asyncio
import os  # <--- (修改 1) 匯入 os 以讀取環境變數
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command

# 匯入主程式 app 與依賴
from app.main import app
from app.core.database import get_db
from app.core.config import settings
from app.core.redis import redis_manager

# --- (修改 2) 動態設定連線字串 ---
# 本地開發預設值 (對應 docker-compose.test.yml)
DEFAULT_TEST_DB_URL = "mysql+aiomysql://root:root@localhost:3307/freelancer_test_db"
DEFAULT_TEST_REDIS_URL = "redis://localhost:6380"

# 優先讀取環境變數 (CI 會設定)，若無則使用本地預設值
TEST_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_TEST_DB_URL)
TEST_REDIS_URL = os.getenv("REDIS_URL", DEFAULT_TEST_REDIS_URL)

# 強制覆寫 Settings
settings.DATABASE_URL = TEST_DATABASE_URL
settings.REDIS_URL = TEST_REDIS_URL
settings.FILE_STORAGE_MODE = "local"
# -------------------------------

# 2. 建立測試用的 Engine
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

TestingSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

# 使用絕對路徑的 Migration Fixture
@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    (Session Scope) 測試開始前執行 Alembic Migrations
    """
    # 1. 計算專案根目錄的絕對路徑
    base_dir = Path(__file__).resolve().parent.parent.parent
    
    # 2. 指定 alembic.ini 的絕對路徑
    alembic_ini_path = base_dir / "alembic.ini"
    
    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"找不到 alembic.ini，請確認路徑: {alembic_ini_path}")

    # 3. 建立 Alembic Config 物件
    alembic_cfg = Config(str(alembic_ini_path))
    
    # 4. 強制設定 script_location 為絕對路徑
    script_location = base_dir / "alembic"
    alembic_cfg.set_main_option("script_location", str(script_location))
    
    # 5. 強制覆寫資料庫連線字串 (確保遷移用到的是測試庫)
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # 6. 執行 upgrade head
    command.upgrade(alembic_cfg, "head")
    
    yield

@pytest.fixture(scope="function")
async def db_session():
    """每個測試執行前開啟 Transaction，執行後 Rollback"""
    connection = await test_engine.connect()
    transaction = await connection.begin()
    
    session = TestingSessionLocal(bind=connection)
    yield session
    
    await session.close()
    await transaction.rollback()
    await connection.close()

@pytest.fixture(scope="function")
async def client(db_session):
    """覆寫 FastAPI 的 get_db 依賴"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # 使用 ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear()

# --- Auth Helpers ---

@pytest.fixture(scope="function")
async def freelancer_auth_headers(client):
    """
    (Helper Fixture) 快速註冊、登入並建立 Profile 的「自由工作者」
    """
    email = "integration_freelancer@example.com"
    password = "TestPassword123"
    
    await client.post("/auth/register", json={
        "email": email,
        "password": password,
        "role": "自由工作者"
    })
    
    response = await client.post("/auth/token", data={
        "username": email,
        "password": password
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 建立 Freelancer Profile
    await client.post("/profiles/me", headers=headers, json={
        "full_name": "Test Freelancer",
        "bio": "Experienced developer",
        "phone": "0912345678",
    })

    return headers

@pytest.fixture(scope="function")
async def employer_auth_headers(client):
    """
    (Helper Fixture) 快速註冊、登入並建立 Profile 的「雇主」
    """
    email = "integration_employer@example.com"
    password = "TestPassword123"
    
    await client.post("/auth/register", json={
        "email": email,
        "password": password,
        "role": "雇主"
    })
    
    response = await client.post("/auth/token", data={
        "username": email,
        "password": password
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 建立 Employer Profile
    await client.post("/profiles/me", headers=headers, json={
        "company_name": "Test Company Inc.",
        "company_bio": "We are a great company.",
        "contact_email": "contact@example.com"
    })

    return headers

@pytest.fixture(scope="session", autouse=True)
async def app_lifespan():
    """
    (Session Scope) 模擬 FastAPI 的 Lifespan (Startup/Shutdown)
    """
    # 1. Startup
    redis_manager.initialize()
    
    yield
    
    # 2. Shutdown
    try:
        await redis_manager.close()
    except RuntimeError as e:
        # 如果 Loop 已經關了，Redis 斷線會報錯，但我們可以安全忽略
        if "Event loop is closed" not in str(e):
            raise
    except Exception:
        pass