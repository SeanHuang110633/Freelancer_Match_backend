# tests/integration/test_auth_flow.py

import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.user import User

# 標記為 asyncio 測試，這是 pytest-asyncio 的要求
@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient, db_session):
    """
    【整合測試 P0】驗證完整的註冊與登入流程
    1. 透過 API 註冊使用者
    2. 直接查詢 DB 確認資料已寫入 (驗證 Transaction 運作)
    3. 透過 API 登入取得 Token
    4. 使用 Token 存取受保護的 /users/me 路由
    """
    # 1. Arrange (準備資料)
    email = "flow_test_user@example.com"
    password = "FlowPassword123"
    role = "自由工作者"

    # 2. Act: 註冊 (Register)
    response_reg = await client.post("/auth/register", json={
        "email": email,
        "password": password,
        "role": role
    })
    
    # Assert: 註冊成功
    assert response_reg.status_code == 201, f"註冊失敗: {response_reg.text}"
    data_reg = response_reg.json()
    assert data_reg["email"] == email
    assert "user_id" in data_reg
    new_user_id = data_reg["user_id"]

    # 3. Assert: 驗證資料庫 (DB Check)
    # 這裡我們使用 db_session 直接查詢，這是在同一個 Transaction 內
    stmt = select(User).where(User.email == email)
    result = await db_session.execute(stmt)
    user_db = result.scalars().first()
    
    assert user_db is not None, "資料庫中找不到剛註冊的使用者"
    assert user_db.user_id == new_user_id
    assert user_db.role.value == role # 注意: Enum 比較需用 .value 或直接比對 Enum 物件

    # 4. Act: 登入 (Login)
    response_login = await client.post("/auth/token", data={
        "username": email,
        "password": password
    })
    
    # Assert: 登入成功並取得 Token
    assert response_login.status_code == 200, f"登入失敗: {response_login.text}"
    token_data = response_login.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 5. Act: 存取受保護資源 (Access Protected Route)
    response_me = await client.get("/users/me", headers=headers)
    
    # Assert: 身分驗證成功
    assert response_me.status_code == 200
    data_me = response_me.json()
    assert data_me["email"] == email
    assert data_me["user_id"] == new_user_id

@pytest.mark.asyncio
async def test_duplicate_email_registration(client: AsyncClient):
    """
    【整合測試 P1】驗證重複註冊的錯誤處理 (資料庫約束測試)
    """
    email = "duplicate_test@example.com"
    password = "TestPassword123"
    role = "雇主"

    # 第一次註冊：應該成功
    resp1 = await client.post("/auth/register", json={
        "email": email, "password": password, "role": role
    })
    assert resp1.status_code == 201

    # 第二次註冊：應該失敗 (400 Bad Request)
    resp2 = await client.post("/auth/register", json={
        "email": email, "password": password, "role": role
    })
    
    # 這裡驗證的是 Service 層是否有捕捉到 IntegrityError 並轉拋 400
    assert resp2.status_code == 400
    assert "已經被註冊" in resp2.json()["detail"]