import pytest
import uuid
import time
from playwright.sync_api import Page, Browser, expect

# 測試帳號 (需與資料庫一致)
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

# ==========================================
# 1. API 輔助函式 (用於快速建立測試資料)
# ==========================================

def get_auth_headers(api_request, email, password):
    """登入並取得 Header (含 Token)"""
    res = api_request.post("/auth/token", form={"username": email, "password": password})
    assert res.ok, f"Login failed for {email}: {res.text()}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def chat_setup(playwright, base_url):
    """
    Fixture: 
    1. 透過 API 建立一個專案
    2. 透過 API 建立該專案的聊天室 (邀請 Freelancer)
    回傳: (project_title, employer_headers, freelancer_headers)
    """
    api = playwright.request.new_context(base_url="http://localhost:8000")
    
    # 1. 取得雙方 Token
    emp_headers = get_auth_headers(api, EMPLOYER_EMAIL, PASSWORD)
    free_headers = get_auth_headers(api, FREELANCER_EMAIL, PASSWORD)
    
    # 2. 查詢 Freelancer ID
    res_me = api.get("/users/me", headers=free_headers)
    assert res_me.ok
    freelancer_id = res_me.json()["user_id"]

    # 3. 雇主建立案件
    unique_id = uuid.uuid4().hex[:6]
    project_title = f"Chat Test {unique_id}"
    res_proj = api.post("/projects/", headers=emp_headers, data={
        "title": project_title,
        "description": "Project for chat testing",
        "budget_min": 1000,
        "budget_max": 2000,
        "skill_tag_ids": []
    })
    assert res_proj.ok
    project_id = res_proj.json()["project_id"]

    # 4. 建立聊天室
    res_room = api.post("/messages/rooms", headers=emp_headers, data={
        "project_id": project_id,
        "invited_user_id": freelancer_id
    })
    assert res_room.ok
    room_data = res_room.json()
    
    print(f"✅ [Setup] 聊天室已建立。Project: {project_title}")
    
    yield project_title
    
    api.dispose()

# ==========================================
# 2. UI 測試腳本
# ==========================================

def login_ui(page: Page, base_url: str, email: str):
    """UI 登入輔助函式"""
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

def test_chat_realtime_flow(browser: Browser, base_url: str, chat_setup):
    """
    驗證即時通訊流程 (M8)
    """
    project_title = chat_setup

    # 1. 建立兩個 Context (模擬雙方)
    context_emp = browser.new_context()
    context_free = browser.new_context()
    
    page_emp = context_emp.new_page()
    page_free = context_free.new_page()

    # 2. 雙方登入
    login_ui(page_emp, base_url, EMPLOYER_EMAIL)
    login_ui(page_free, base_url, FREELANCER_EMAIL)

    # 3. 進入聊天頁
    page_emp.goto(f"{base_url}/chat")
    page_free.goto(f"{base_url}/chat")

    # 4. 點擊聊天室 (依賴 ChatView 的 getRoomDisplayName 邏輯)
    print(f"⏳ 尋找聊天室: {project_title}")
    
    # 這裡會等待左側選單出現該專案名稱
    page_emp.locator(".room-list-menu").get_by_text(project_title).click()
    page_free.locator(".room-list-menu").get_by_text(project_title).click()

    # 5. 驗證連線狀態 (ChatView.vue 中的 el-tag)
    # 這是 ChatBox 解除禁用按鈕的前置條件
    print("⏳ 等待 WebSocket 連線...")
    expect(page_emp.locator(".el-tag").filter(has_text="已連線")).to_be_visible(timeout=10000)
    expect(page_free.locator(".el-tag").filter(has_text="已連線")).to_be_visible(timeout=10000)
    print("✅ 雙方 WebSocket 已連線")

    # 6. 雇主發送訊息
    msg_to_free = f"Hello Free {uuid.uuid4().hex[:4]}"
    
    # 【更新點 1】使用 placeholder 定位輸入框 (ChatBox.vue)
    emp_input = page_emp.get_by_placeholder("輸入訊息...")
    emp_input.fill(msg_to_free)
    
    # 【更新點 2】定位發送按鈕
    # 按鈕位於 .message-input-area 內，且是唯一的 button
    send_btn_emp = page_emp.locator(".message-input-area button")
    
    # 確保按鈕已啟用 (因為有 :disabled 邏輯)
    expect(send_btn_emp).to_be_enabled() 
    send_btn_emp.click()

    # 7. 驗證：工作者收到訊息
    print("⏳ 驗證工作者收到訊息...")
    # 【更新點 3】驗證訊息是否出現在 .message-content 中 (ChatBox.vue)
    expect(page_free.locator(".message-content").filter(has_text=msg_to_free)).to_be_visible(timeout=5000)
    print("✅ 工作者成功收到訊息 (Real-time)")

    # 8. 工作者回覆
    msg_to_emp = f"Hi Emp {uuid.uuid4().hex[:4]}"
    
    page_free.get_by_placeholder("輸入訊息...").fill(msg_to_emp)
    
    # 這次我們試試看按 Enter 鍵發送 (測試 @keydown.enter.prevent)
    page_free.get_by_placeholder("輸入訊息...").press("Enter")

    # 9. 驗證：雇主收到回覆
    print("⏳ 驗證雇主收到回覆...")
    expect(page_emp.locator(".message-content").filter(has_text=msg_to_emp)).to_be_visible(timeout=5000)
    print("✅ 雇主成功收到回覆 (Real-time)")

    # 10. 清理
    context_emp.close()
    context_free.close()