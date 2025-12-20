import pytest
import uuid
import re  # <--- 新增這行
from playwright.sync_api import Page, Browser, expect

# 真實測試帳號
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

# ==========================================
# 1. API 資料準備 (Fixtures)
# ==========================================

def get_token(api_request, email, password):
    res = api_request.post("/auth/token", form={"username": email, "password": password})
    assert res.ok
    return res.json()["access_token"]

@pytest.fixture(scope="function")
def say_hi_setup(playwright, base_url):
    """
    [場景 A 前置]：
    1. 確保雇主有一個「招募中」的案件。
    2. 獲取工作者的 User ID。
    """
    api = playwright.request.new_context(base_url="http://localhost:8000")
    
    # 1. 雇主登入並建立案件
    emp_token = get_token(api, EMPLOYER_EMAIL, PASSWORD)
    unique_id = uuid.uuid4().hex[:6]
    project_title = f"SayHi Project {unique_id}"
    
    res_proj = api.post("/projects/", headers={"Authorization": f"Bearer {emp_token}"}, data={
        "title": project_title,
        "description": "Project for Say Hi testing",
        "budget_min": 1000, "budget_max": 2000, "skill_tag_ids": []
    })
    assert res_proj.ok
    
    # 2. 獲取工作者 ID (為了組出 URL)
    free_token = get_token(api, FREELANCER_EMAIL, PASSWORD)
    res_me = api.get("/users/me", headers={"Authorization": f"Bearer {free_token}"})
    freelancer_id = res_me.json()["user_id"]
    
    api.dispose()
    return project_title, freelancer_id

@pytest.fixture(scope="function")
def contract_chat_setup(playwright, base_url):
    """
    [場景 B 前置]：
    建立一個已成立的合約 (Project -> Proposal -> Contract)
    """
    api = playwright.request.new_context(base_url="http://localhost:8000")
    emp_token = get_token(api, EMPLOYER_EMAIL, PASSWORD)
    free_token = get_token(api, FREELANCER_EMAIL, PASSWORD)

    # 1. 建立案件
    proj_title = f"Contract Chat {uuid.uuid4().hex[:6]}"
    res_proj = api.post("/projects/", headers={"Authorization": f"Bearer {emp_token}"}, data={
        "title": proj_title, "description": "desc", "budget_min": 1000, "budget_max": 2000, "skill_tag_ids": []
    })
    project_id = res_proj.json()["project_id"]

    # 2. 提案
    res_prop = api.post(f"/projects/{project_id}/proposals", headers={"Authorization": f"Bearer {free_token}"}, multipart={
        "brief_description": "I can do it",
        "attachment": ("dummy.pdf", b"%PDF...", "application/pdf")
    })
    proposal_id = res_prop.json()["proposal_id"]

    # 3. 接受提案並建立合約
    api.patch(f"/proposals/{proposal_id}/status", headers={"Authorization": f"Bearer {emp_token}"}, data={"status": "已接受"})
    res_contract = api.post("/contracts/", headers={"Authorization": f"Bearer {emp_token}"}, data={"proposal_id": proposal_id})
    contract_id = res_contract.json()["contract_id"]

    api.dispose()
    return contract_id, proj_title

# ==========================================
# 2. UI 輔助函式
# ==========================================

def login_ui(page: Page, base_url: str, email: str):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

# ==========================================
# 3. 測試案例
# ==========================================

def test_scenario_a_say_hi(browser: Browser, base_url: str, say_hi_setup):
    """
    場景 A: 雇主在工作者詳情頁點擊 'Say Hi'
    驗證重點：
    1. Dialog 彈出並顯示招募中的案件。
    2. 選擇案件後，能成功建立聊天室並跳轉。
    """
    project_title, freelancer_id = say_hi_setup
    
    page = browser.new_page()
    
    # 1. 雇主登入
    login_ui(page, base_url, EMPLOYER_EMAIL)

    # 2. 進入工作者詳情頁
    target_url = f"{base_url}/freelancers/{freelancer_id}"
    page.goto(target_url)

    # 3. 點擊 Say Hi
    # (FreelancerDetailView.vue: <el-button ... @click="handleSayHi">Say Hi</el-button>)
    say_hi_btn = page.get_by_role("button", name="Say Hi")
    expect(say_hi_btn).to_be_visible()
    say_hi_btn.click()

    # 4. 驗證 Dialog 出現
    dialog = page.locator(".el-dialog", has_text="發起對話邀請")
    expect(dialog).to_be_visible()

    # 5. 操作 Element Plus 的 Select 元件 (這比較 tricky)
    # 先點擊 select 觸發 dropdown
    page.locator(".el-select").click()
    
    # 在 dropdown (通常會 render 在 body 結尾) 中選擇剛建立的專案
    # 使用 get_by_role("option") 或 text
    option = page.locator(".el-select-dropdown__item").filter(has_text=project_title)
    expect(option).to_be_visible()
    option.click()

    # 6. 確認並開始聊天
    confirm_btn = dialog.get_by_role("button", name="開始聊天")
    expect(confirm_btn).not_to_be_disabled() # 確保按鈕已啟用
    confirm_btn.click()

    # 7. 驗證跳轉與聊天室建立
    page.wait_for_url(re.compile(f"^{base_url}/chat.*"))
    
    # 驗證左側列表出現該專案名稱 (ChatView 邏輯)
    expect(page.locator(".room-list-menu")).to_contain_text(project_title)
    
    # 驗證中間 Header 顯示專案名稱 (代表已選中)
    expect(page.locator(".chat-box-header")).to_contain_text(project_title)

    print("✅ [Scenario A] Say Hi 流程驗證成功")
    page.close()


def test_scenario_b_contract_chat(browser: Browser, base_url: str, contract_chat_setup):
    """
    場景 B: 工作者在合約詳情頁點擊 '前往聊天室'
    驗證重點：
    1. 點擊按鈕後直接跳轉至 /chat。
    2. 自動選中該合約對應的聊天室。
    """
    contract_id, project_title = contract_chat_setup
    
    page = browser.new_page()

    # 1. 工作者登入
    login_ui(page, base_url, FREELANCER_EMAIL)

    # 2. 進入合約詳情
    page.goto(f"{base_url}/contracts/{contract_id}")

    # 3. 點擊 '前往聊天室'
    # (ContractView.vue: <el-button ... @click="handleGoToChat">前往聊天室</el-button>)
    chat_btn = page.get_by_role("button", name="前往聊天室")
    expect(chat_btn).to_be_visible()
    chat_btn.click()

    # 4. 驗證跳轉
    page.wait_for_url(f"{base_url}/chat")

    # 5. 驗證是否自動選中正確的房間
    # 檢查 active 的 menu item 是否包含專案標題
    active_menu_item = page.locator(".el-menu-item.is-active")
    expect(active_menu_item).to_contain_text(project_title)

    # 檢查 Header
    expect(page.locator(".chat-box-header")).to_contain_text(project_title)

    print("✅ [Scenario B] 合約前往聊天室流程驗證成功")
    page.close()