import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.auth_service import AuthService
from app.schemas.user_schema import UserCreate
from app.models.user import User, UserRoleEnum

# ==========================================
# Part 1: 登入驗證 (Authentication)
# ==========================================

@pytest.mark.asyncio
async def test_authenticate_user_success(mock_db_session, mock_user_freelancer, mocker):
    """測試：帳號密碼正確且未停權 -> 登入成功"""
    # 1. Arrange
    service = AuthService(mock_db_session)
    
    # Mock Repo: 找到使用者
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=mock_user_freelancer)
    
    # Mock Password Verify: 驗證成功
    # 注意：要 Patch service 模組內匯入的 verify_password
    mocker.patch("app.services.auth_service.verify_password", return_value=True)

    # 2. Act
    user = await service.authenticate_user("worker@example.com", "correct_password")

    # 3. Assert
    assert user is not None
    assert user.user_id == mock_user_freelancer.user_id

@pytest.mark.asyncio
async def test_authenticate_user_not_found(mock_db_session, mocker):
    """測試：帳號不存在 -> 回傳 None"""
    service = AuthService(mock_db_session)
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=None)

    user = await service.authenticate_user("wrong@email.com", "password")
    
    assert user is None

@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(mock_db_session, mock_user_freelancer, mocker):
    """測試：密碼錯誤 -> 回傳 None"""
    service = AuthService(mock_db_session)
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=mock_user_freelancer)
    
    # Mock verify_password 回傳 False
    mocker.patch("app.services.auth_service.verify_password", return_value=False)

    user = await service.authenticate_user("worker@example.com", "wrong_password")
    
    assert user is None

@pytest.mark.asyncio
async def test_authenticate_user_inactive_banned(mock_db_session, mocker):
    """測試：帳號被停權 (is_active=False) -> 回傳 None"""
    service = AuthService(mock_db_session)
    
    # 模擬被停權的使用者
    banned_user = User(email="bad@guy.com", is_active=False, password_hash="hash")
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=banned_user)

    user = await service.authenticate_user("bad@guy.com", "password")
    
    # 即使密碼正確 (假設 verify_password 為 True 也不應該過，但邏輯上先檢查 active 比較高效)
    assert user is None

# ==========================================
# Part 2: 註冊邏輯 (Registration)
# ==========================================

@pytest.mark.asyncio
async def test_register_user_success(mock_db_session, mocker):
    """測試：成功註冊新使用者"""
    service = AuthService(mock_db_session)
    user_data = UserCreate(email="new@user.com", password="password123", role="自由工作者")

    # 1. Mock: Email 未被註冊
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=None)
    
    # 2. Mock: 密碼雜湊函式
    mock_hash = mocker.patch("app.services.auth_service.get_password_hash", return_value="hashed_123")
    
    # 3. Mock: UUID 生成 (為了驗證方便)
    mocker.patch("app.services.auth_service.uuid.uuid4", return_value="uuid-new")

    # 4. Mock: Repo create
    # 模擬 Repo 回傳建立後的 User 物件
    expected_user = User(user_id="uuid-new", email="new@user.com", role=UserRoleEnum.freelancer)
    mock_create = mocker.patch.object(service.user_repo, 'create_user', return_value=expected_user)

    # Act
    result = await service.register_user(user_data)

    # Assert
    assert result.user_id == "uuid-new"
    mock_hash.assert_called_once_with("password123") # 確保密碼有被 Hash
    
    # 驗證 create_user 被呼叫的參數
    mock_create.assert_called_once()
    created_user_arg = mock_create.call_args[0][0]
    assert created_user_arg.password_hash == "hashed_123" # 確保存入的是 Hash 值
    assert created_user_arg.email == "new@user.com"

@pytest.mark.asyncio
async def test_register_user_fail_duplicate_email(mock_db_session, mock_user_freelancer, mocker):
    """測試：註冊重複 Email 應報錯"""
    service = AuthService(mock_db_session)
    # (修正) 提供長度 > 8 且合規的密碼
    user_data = UserCreate(email="worker@example.com", password="password123", role="自由工作者")

    # Mock: Email 已存在
    mocker.patch.object(service.user_repo, 'get_user_by_email', return_value=mock_user_freelancer)

    with pytest.raises(HTTPException) as exc:
        await service.register_user(user_data)
    
    assert exc.value.status_code == 400
    assert "This email is already registered." in exc.value.detail

# ==========================================
# Part 3: Token 簽發 (Token Generation)
# ==========================================

def test_create_login_token(mock_db_session, mock_user_freelancer, mocker):
    """測試：產生 JWT Token"""
    service = AuthService(mock_db_session)
    
    # Mock create_access_token 工具函式
    mock_create_jwt = mocker.patch("app.services.auth_service.create_access_token", return_value="fake.jwt.token")

    token = service.create_login_token(mock_user_freelancer)

    assert token == "fake.jwt.token"
    
    # 驗證 Payload 是否正確帶入 User 資訊
    mock_create_jwt.assert_called_once()
    payload = mock_create_jwt.call_args[1]['data'] # kwargs['data']
    assert payload['sub'] == mock_user_freelancer.email
    assert payload['user_id'] == mock_user_freelancer.user_id
    assert payload['role'] == "自由工作者" # 確保 Enum 被轉為字串``