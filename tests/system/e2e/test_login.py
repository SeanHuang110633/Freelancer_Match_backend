import pytest
from playwright.sync_api import Page, expect

# 使用 seed_db.py 中建立的真實帳號
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
VALID_PASSWORD = "1qaz2wsx"
WRONG_PASSWORD = "wrongpassword"

def test_employer_login_success(page: Page, base_url: str):
    """
    ST-02-A (Happy Path - Employer): 雇主登入成功
    驗證：
    1. 成功跳轉至首頁
    2. LocalStorage 存有 Token
    """
    # 1. 前往登入頁
    page.goto(f"{base_url}/login")

    # 2. 填寫表單 (根據 LoginForm.vue)
    page.get_by_placeholder("Enter your Email").fill(EMPLOYER_EMAIL)
    page.get_by_placeholder("Enter your password").fill(VALID_PASSWORD)

    # 3. 點擊登入
    page.get_by_role("button", name="Login").click()

    # 4. 驗證跳轉
    # 根據 LoginForm.vue: router.push("/")
    # 使用 wait_for_url 確保路由已切換，這是最穩定的等待方式
    page.wait_for_url(f"{base_url}/")
    
    # 5. 驗證 Token 持久化 (驗證 authStore 邏輯)
    token = page.evaluate("localStorage.getItem('access_token')")
    assert token is not None and len(token) > 0, "登入後 access_token 應存在於 LocalStorage"

    # 6. (選用) 驗證 User Data
    user_data = page.evaluate("localStorage.getItem('user_data')")
    assert user_data is not None, "登入後 user_data 應存在"
    assert EMPLOYER_EMAIL in user_data, "user_data 應包含正確的 email"


def test_freelancer_login_success(page: Page, base_url: str):
    """
    ST-02-B (Happy Path - Freelancer): 工作者登入成功
    驗證：不同角色的帳號也能正常登入
    """
    page.goto(f"{base_url}/login")

    page.get_by_placeholder("Enter your Email").fill(FREELANCER_EMAIL)
    page.get_by_placeholder("Enter your password").fill(VALID_PASSWORD)
    page.get_by_role("button", name="Login").click()

    # 驗證跳轉
    page.wait_for_url(f"{base_url}/")
    
    # 驗證 Token
    token = page.evaluate("localStorage.getItem('access_token')")
    assert token is not None, "工作者登入後 access_token 應存在"


def test_login_failure_wrong_password(page: Page, base_url: str):
    """
    ST-02-C (Error Handling): 密碼錯誤
    驗證：
    1. 停留在登入頁 (不跳轉)
    2. 顯示紅色錯誤提示框
    """
    page.goto(f"{base_url}/login")

    # 1. 填寫錯誤密碼
    page.get_by_placeholder("Enter your Email").fill(EMPLOYER_EMAIL)
    page.get_by_placeholder("Enter your password").fill(WRONG_PASSWORD) # 錯誤

    # 2. 點擊登入
    page.get_by_role("button", name="Login").click()

    # 3. 驗證錯誤訊息出現
    # 根據 LoginForm.vue: errorMessage.value = "Login failed..."
    # 錯誤框 class 通常為 el-alert--error
    error_alert = page.locator(".el-alert--error")
    
    # 等待錯誤框出現 (預設 5s，若後端回應慢可自動 retry)
    expect(error_alert).to_be_visible()
    
    # 驗證錯誤文字內容
    expect(error_alert).to_contain_text("Login failed")
    expect(error_alert).to_contain_text("check your email or password")

    # 4. 驗證 URL 依然是 /login (未跳轉)
    expect(page).to_have_url(f"{base_url}/login")
    
    # 5. 驗證 Token 未被寫入 (確保登入失敗沒有髒資料)
    token = page.evaluate("localStorage.getItem('access_token')")
    assert token is None, "登入失敗不應寫入 Token"