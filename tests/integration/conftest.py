# tests/integration/conftest.py

import asyncio
import os
import pytest
from pathlib import Path  # <--- (新增) 務必匯入
from httpx import AsyncClient, ASGITransport # <--- (修改 1) 新增 ASGITransport
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

# 1. 定義整合測試專用的真實 DB 連線
TEST_DATABASE_URL = "mysql+aiomysql://root:root@localhost:3307/freelancer_test_db"
TEST_REDIS_URL = "redis://localhost:6380"

# 強制覆寫 Settings
settings.DATABASE_URL = TEST_DATABASE_URL
settings.REDIS_URL = TEST_REDIS_URL
settings.FILE_STORAGE_MODE = "local"

# 2. 建立測試用的 Engine
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

TestingSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

# @pytest.fixture(scope="session")
# def event_loop():
#     """
#     建立 Session 等級的 Event Loop，並設定為當前 Loop。
#     這對於 session scope 的 fixture (如 app_lifespan) 至關重要。
#     """
#     try:
#         loop = asyncio.get_running_loop()
#     except RuntimeError:
#         loop = asyncio.new_event_loop()
    
#     yield loop
#     loop.close()

# --- (修正重點) 使用絕對路徑的 Migration Fixture ---
@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    (Session Scope) 測試開始前執行 Alembic Migrations
    """
    # 1. 計算專案根目錄的絕對路徑
    # 目前檔案位置: tests/integration/conftest.py
    # 往上三層回到專案根目錄: freelancer_match_backend/
    base_dir = Path(__file__).resolve().parent.parent.parent
    
    # 2. 指定 alembic.ini 的絕對路徑
    alembic_ini_path = base_dir / "alembic.ini"
    
    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"找不到 alembic.ini，請確認路徑: {alembic_ini_path}")

    # 3. 建立 Alembic Config 物件
    alembic_cfg = Config(str(alembic_ini_path))
    
    # 4. (關鍵修正) 強制設定 script_location 為絕對路徑
    # 這樣無論 pytest 在哪裡執行，都能找到 'alembic/' 資料夾
    script_location = base_dir / "alembic"
    alembic_cfg.set_main_option("script_location", str(script_location))
    
    # 5. 強制覆寫資料庫連線字串 (確保遷移用到的是測試庫)
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # 6. 執行 upgrade head
    command.upgrade(alembic_cfg, "head")
    
    yield
    
    # (可選) 測試結束後不做降級，保留資料庫狀態供除錯，或由 Transaction Rollback 處理
    # command.downgrade(alembic_cfg, "base")

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
    
    # --- (修改 2) 使用 ASGITransport ---
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # ----------------------------------
    
    app.dependency_overrides.clear()

# --- Auth Helpers ---

@pytest.fixture(scope="function")
async def freelancer_auth_headers(client):
    """
    (Helper Fixture)
    快速註冊、登入並建立 Profile 的「自由工作者」，回傳帶有 Bearer Token 的 Headers。
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

    # 3. (新增) 建立 Freelancer Profile
    await client.post("/profiles/me", headers=headers, json={
        "full_name": "Test Freelancer",
        "bio": "Experienced developer",
        "phone": "0912345678",
        # "visibility": "公開" (預設)
    })

    return headers

@pytest.fixture(scope="function")
async def employer_auth_headers(client):
    """
    (Helper Fixture)
    快速註冊、登入並建立 Profile 的「雇主」。
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

    # (新增) 建立 Employer Profile
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
    
    # 2. Shutdown (修改：加入 try-except)
    try:
        await redis_manager.close()
    except RuntimeError as e:
        # 如果 Loop 已經關了，Redis 斷線會報錯，但我們可以安全忽略
        if "Event loop is closed" not in str(e):
            raise
    except Exception:
        # 其他錯誤也不要讓測試失敗 (因為這是在 Teardown)
        pass