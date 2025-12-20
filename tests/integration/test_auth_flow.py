import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.user import User, UserRoleEnum

# 使用 pytest-asyncio 標記
@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient, db_session):
    """
    【整合測試 P0】驗證完整的註冊與登入流程
    
    測試場景：
    1. 使用者註冊 (Register)
    2. 驗證資料庫是否寫入正確資料 (DB Verification)
    3. 使用者登入取得 JWT (Login)
    4. 使用 JWT 存取受保護路由 (Protected Route)
    """
    
    # 1. Arrange (準備資料)
    # 使用與其他測試不衝突的唯一 Email
    email = "integration_flow_user@example.com" 
    password = "FlowPassword123"
    role_str = "自由工作者" # 對應 UserRoleEnum.freelancer.value

    # 2. Act: 註冊 (Register)
    # API 規格: POST /auth/register, Body: JSON
    response_reg = await client.post("/auth/register", json={
        "email": email,
        "password": password,
        "role": role_str
    })
    
    # Assert: 註冊成功
    assert response_reg.status_code == 201, f"註冊失敗回應: {response_reg.text}"
    data_reg = response_reg.json()
    assert data_reg["email"] == email
    assert data_reg["role"] == role_str
    assert "user_id" in data_reg
    assert data_reg["is_active"] is True
    
    new_user_id = data_reg["user_id"]

    # 3. Assert: 驗證資料庫 (DB Check)
    # 透過 db_session 直接查詢，驗證資料是否確實寫入 DB
    stmt = select(User).where(User.email == email)
    result = await db_session.execute(stmt)
    user_db = result.scalars().first()
    
    assert user_db is not None, "資料庫中找不到剛註冊的使用者"
    assert user_db.user_id == new_user_id
    # 注意：user_db.role 是 Enum 物件，需取 .value 進行字串比對
    assert user_db.role.value == role_str 

    # 4. Act: 登入 (Login)
    # API 規格: POST /auth/token, Body: Form-Data (application/x-www-form-urlencoded)
    # OAuth2PasswordRequestForm 要求欄位為 'username' 與 'password'
    response_login = await client.post("/auth/token", data={
        "username": email,
        "password": password
    })
    
    # Assert: 登入成功並取得 Token
    assert response_login.status_code == 200, f"登入失敗回應: {response_login.text}"
    token_data = response_login.json()
    
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    
    access_token = token_data["access_token"]
    
    # 5. Act: 存取受保護資源 (Access Protected Route)
    # 使用 Bearer Token 呼叫 /users/me
    headers = {"Authorization": f"Bearer {access_token}"}
    response_me = await client.get("/users/me", headers=headers)
    
    # Assert: 身分驗證成功，且回傳資料正確
    assert response_me.status_code == 200, f"存取受保護路由失敗: {response_me.text}"
    data_me = response_me.json()
    assert data_me["email"] == email
    assert data_me["user_id"] == new_user_id
    assert data_me["role"] == role_str


@pytest.mark.asyncio
async def test_duplicate_email_registration(client: AsyncClient):
    """
    【整合測試 P1】驗證重複註冊的錯誤處理
    
    測試場景：
    1. 註冊一個新的 Email (預期成功)
    2. 使用相同 Email 再次註冊 (預期失敗，回傳 400)
    """
    # Arrange
    email = "duplicate_test_user@example.com"
    password = "TestPassword123"
    role = "雇主"

    # Act 1: 第一次註冊
    resp1 = await client.post("/auth/register", json={
        "email": email, 
        "password": password, 
        "role": role
    })
    assert resp1.status_code == 201

    # Act 2: 第二次註冊 (相同 Email)
    resp2 = await client.post("/auth/register", json={
        "email": email, 
        "password": password, 
        "role": role
    })
    
    # Assert: 應該被 Service 層攔截並回傳 400 Bad Request
    assert resp2.status_code == 400
    error_detail = resp2.json()["detail"]
    
    # 驗證錯誤訊息內容 (需對應 AuthService 中的 exception detail)
    assert "This email is already registered." in error_detail