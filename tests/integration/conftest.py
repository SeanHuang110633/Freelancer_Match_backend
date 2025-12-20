# tests/integration/conftest.py

import asyncio
import os
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command
import redis.asyncio as aioredis

# 匯入主程式 app 與依賴
from app.main import app
from app.core.database import get_db
from app.core.config import settings
from app.core.redis import redis_manager

# --- 設定連線字串 ---
DEFAULT_TEST_DB_URL = "mysql+aiomysql://root:root@localhost:3307/freelancer_test_db"
DEFAULT_TEST_REDIS_URL = "redis://localhost:6380"

TEST_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_TEST_DB_URL)
TEST_REDIS_URL = os.getenv("REDIS_URL", DEFAULT_TEST_REDIS_URL)

settings.DATABASE_URL = TEST_DATABASE_URL
settings.REDIS_URL = TEST_REDIS_URL
settings.FILE_STORAGE_MODE = "local"
settings.REDIS_POOL_SIZE = 100

# 【修正 1】移除手動定義的 event_loop fixture
# pytest-asyncio 現在會根據 pytest.ini 中的設定自動處理 Loop
# @pytest.fixture(scope="session")
# def event_loop(): ... (刪除這段)

# --- DB Engine (Session Scope) ---
@pytest.fixture(scope="session")
async def test_engine():
    # 這裡會自動使用 pytest-asyncio 提供的 session loop
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
    yield engine
    await engine.dispose()

@pytest.fixture(scope="session")
def TestingSessionLocal(test_engine):
    return sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

# --- Migrations (Session Scope) ---
@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    base_dir = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = base_dir / "alembic.ini"
    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"找不到 alembic.ini: {alembic_ini_path}")
    
    alembic_cfg = Config(str(alembic_ini_path))
    script_location = base_dir / "alembic"
    alembic_cfg.set_main_option("script_location", str(script_location))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    
    command.upgrade(alembic_cfg, "head")
    yield

# --- DB Session (Function Scope) ---
@pytest.fixture(scope="function")
async def db_session(test_engine, TestingSessionLocal):
    # 每個測試開始前，建立連線與 Transaction
    connection = await test_engine.connect()
    transaction = await connection.begin()
    
    # 綁定連線到 Session
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    # 測試結束後，關閉 Session 並 Rollback Transaction
    await session.close()
    await transaction.rollback()
    await connection.close()

# --- Redis Lifecycle (Session Scope) ---
@pytest.fixture(scope="session", autouse=True)
async def init_test_redis():
    redis_manager.initialize()
    yield
    await redis_manager.close()

@pytest.fixture(scope="function", autouse=True)
async def clean_redis():
    """每個測試前清空 Redis"""
    if not redis_manager.pool:
        return

    try:
        client = aioredis.Redis(connection_pool=redis_manager.pool)
        await client.flushall()
        await client.aclose()
    except Exception as e:
        print(f"Warning: Redis flush failed: {e}")

# --- Client (Function Scope) ---
@pytest.fixture(scope="function")
async def client(db_session):
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    
    # 【修正 2】使用 async with 來確保 client 的生命週期正確管理
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear()

# --- Auth Helpers (Function Scope) ---
@pytest.fixture(scope="function")
async def freelancer_auth_headers(client):
    """
    建立一個自由工作者帳號並登入，回傳帶有 Token 的 Headers
    """
    email = "integration_freelancer@example.com"
    password = "TestPassword123"
    
    # 1. 註冊
    await client.post("/auth/register", json={
        "email": email, 
        "password": password, 
        "role": "自由工作者"
    })
    
    # 2. 登入
    response = await client.post("/auth/token", data={
        "username": email, 
        "password": password
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. 建立 Profile (避免測試時因為沒 Profile 報錯)
    # 忽略 400 錯誤 (如果因為測試順序導致已存在)
    await client.post("/profiles/me", headers=headers, json={
        "full_name": "Test Freelancer", 
        "bio": "Dev", 
        "phone": "0912345678"
    })
    
    return headers

@pytest.fixture(scope="function")
async def employer_auth_headers(client):
    """
    建立一個雇主帳號並登入，回傳帶有 Token 的 Headers
    """
    email = "integration_employer@example.com"
    password = "TestPassword123"
    
    # 1. 註冊
    await client.post("/auth/register", json={
        "email": email, 
        "password": password, 
        "role": "雇主"
    })
    
    # 2. 登入
    response = await client.post("/auth/token", data={
        "username": email, 
        "password": password
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. 建立 Profile
    await client.post("/profiles/me", headers=headers, json={
        "company_name": "Test Co", 
        "company_bio": "Good Company", 
        "contact_email": "contact@example.com"
    })
    
    return headers