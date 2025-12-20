import pytest
import uuid
import re
from playwright.sync_api import Page, expect

# 引用 seed data 中已存在的帳號 (用於測試重複註冊)
EXISTING_EMAIL = "e1@11.com"

def test_register_happy_path(page: Page, base_url: str):
    """
    ST-01-A (Happy Path): 驗證新使用者可以成功註冊
    """
    # 1. 產生一個隨機且唯一的 Email
    new_email = f"auto_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    # 2. 前往首頁/登入頁
    page.goto(f"{base_url}/login")

    # 3. 切換到註冊模式
    page.get_by_text("Register right now").click()

    # 4. 驗證已進入註冊畫面
    register_btn = page.get_by_role("button", name="Register")
    expect(register_btn).to_be_visible()

    # 5. 填寫註冊表單
    page.get_by_placeholder("Enter your Email").fill(new_email)
    page.get_by_placeholder("Enter password (at least 8 mixed characters)").fill(password)
    page.get_by_placeholder("Re-enter your password").fill(password)

    # 6. 選擇角色
    page.locator("label").filter(has_text="Employer").click()

    # 7. 提交
    register_btn.click()

    # 8. 驗證結果 (增強版)
    # 我們將 timeout 延長至 10 秒，並加入錯誤偵測
    try:
        # 優先嘗試尋找成功訊息 (使用文字內容定位更準確)
        expect(page.locator(".el-alert--success")).to_be_visible(timeout=10000)
        
        # 額外確認訊息內容是否正確
        success_text = page.locator(".el-alert--success").text_content()
        assert "registered successfully" in success_text
        assert new_email in success_text

    except AssertionError as e:
        # 如果等待成功訊息失敗，檢查是否出現了錯誤訊息
        if page.locator(".el-alert--error").is_visible():
            error_msg = page.locator(".el-alert--error").text_content()
            # 拋出更明確的錯誤，讓開發者知道後端回傳了什麼錯誤
            raise AssertionError(f"❌ 註冊失敗，畫面顯示錯誤訊息: {error_msg}")
        
        # 如果也沒有錯誤訊息，那就真的是逾時或無反應
        raise AssertionError(f"❌ 註冊逾時 (10s) 且無任何回饋訊息。原始錯誤: {e}")


def test_register_password_mismatch(page: Page, base_url: str):
    """
    ST-01-B (Frontend Validation): 驗證密碼不一致時，前端應阻擋並顯示錯誤
    """
    page.goto(f"{base_url}/login")
    page.get_by_text("Register right now").click()

    # 1. 填寫不一致的密碼
    page.get_by_placeholder("Enter your Email").fill("mismatch@test.com")
    page.get_by_placeholder("Enter password (at least 8 mixed characters)").fill("password123")
    page.get_by_placeholder("Re-enter your password").fill("password999") # 不一樣

    # 2. 提交
    page.get_by_role("button", name="Register").click()

    # 3. 驗證錯誤訊息 (前端阻擋，不應發送 API)
    # 根據 RegisterForm.vue: errorMessage.value = "Passwords do not match..."
    error_alert = page.locator(".el-alert--error")
    expect(error_alert).to_be_visible()
    expect(error_alert).to_contain_text("Passwords do not match")


def test_register_duplicate_email(page: Page, base_url: str):
    """
    ST-01-C (Backend Validation): 驗證使用已存在的 Email 註冊會被後端拒絕
    """
    page.goto(f"{base_url}/login")
    page.get_by_text("Register right now").click()

    # 1. 使用已存在的 Email
    page.get_by_placeholder("Enter your Email").fill(EXISTING_EMAIL)
    page.get_by_placeholder("Enter password (at least 8 mixed characters)").fill("password123")
    page.get_by_placeholder("Re-enter your password").fill("password123")

    # 2. 提交
    page.get_by_role("button", name="Register").click()

    # 3. 驗證後端錯誤回傳
    # 後端 auth_router 通常回傳 400 Detail: "此 Email 已經被註冊" (或英文)
    # 前端會將 error.response.data.detail 顯示在 alert
    error_alert = page.locator(".el-alert--error")
    expect(error_alert).to_be_visible(timeout=5000)
    
    # 這裡我們只驗證有錯誤跳出，因為後端錯誤訊息可能是中文或英文，視您的後端實作而定
    # 如果確定後端回傳中文，可以加上:
    # expect(error_alert).to_contain_text("已經被註冊")a