import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.user import User, UserRoleEnum


# --- 匯入所有 Models 以解決 SQLAlchemy Registry 問題 ---
# 即使這裡沒直接用到，也必須 import，確保 relationship("ClassName") 能找到對應的 class
from app.models.user import User, UserRoleEnum
from app.models.contract import Contract
from app.models.project import Project
from app.models.proposal import Proposal
from app.models.deliverable import Deliverable  # <--- 這次報錯的主因
from app.models.review import Review            # <--- 預防 Review 相關報錯
from app.models.employer_profile import EmployerProfile
from app.models.freelancer_profile import FreelancerProfile
from app.models.skill_tag import SkillTag, UserSkillTag
from app.models.message import ChatRoom, Message, ChatRoomParticipant
from app.models.notification import Notification
# -----------------------------------------------------------

# --- 1. 資料庫 Session Mock ---

@pytest.fixture
def mock_db_session():
    """
    建立一個假的 AsyncSession。
    Service 層初始化時需要傳入 db，我們傳入這個 mock。
    """
    session = AsyncMock()
    
    # 模擬 commit/refresh/rollback 這些基本操作不報錯
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    # 模擬 execute 回傳的 result 結構 (result.scalars().first() / .all())
    # 預設回傳 None 或 空列表，具體測試案例中可再覆寫 (Override)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = None
    
    session.execute.return_value = mock_result
    
    return session

# --- 2. 使用者 Fixtures (預設假人) ---

@pytest.fixture
def mock_user_freelancer():
    """模擬一個已登入的自由工作者"""
    return User(
        user_id="user_freelancer_001",
        email="worker@example.com",
        password_hash="hashed_secret",
        role=UserRoleEnum.freelancer,
        is_active=True
    )

@pytest.fixture
def mock_user_employer():
    """模擬一個已登入的雇主"""
    return User(
        user_id="user_employer_001",
        email="boss@example.com",
        password_hash="hashed_secret",
        role=UserRoleEnum.employer,
        is_active=True
    )

# --- 3. 全域服務 Mock (防止外部連線) ---

@pytest.fixture(autouse=True)
def mock_settings_env(mocker):
    """
    (自動執行) 確保所有測試都在安全環境下執行。
    強制 Mock 掉設定檔，雖然 pytest.ini 有設，但這裡雙重保險。
    """
    mocker.patch("app.core.config.settings.FILE_STORAGE_MODE", "local")
    # 防止 Redis 連線
    mocker.patch("app.core.config.settings.REDIS_URL", "redis://mock")

@pytest.fixture(autouse=True)
def mock_gcs_client(mocker):
    """
    (自動執行) Mock 掉 Google Cloud Storage Client。
    防止 ProposalService 初始化時報錯或嘗試連線。
    """
    return mocker.patch("google.cloud.storage.Client")

@pytest.fixture(autouse=True)
def mock_redis_client(mocker):
    """
    (自動執行) Mock 掉 Redis Client。
    防止 MessageService 初始化時報錯。
    """
    mock_redis = mocker.patch("redis.asyncio.from_url", new_callable=AsyncMock)
    return mock_redis