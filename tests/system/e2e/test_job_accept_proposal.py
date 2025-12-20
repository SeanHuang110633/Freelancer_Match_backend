import pytest
import uuid
from playwright.sync_api import Page, Browser, expect, APIRequestContext

# 真實測試帳號
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

# ==========================================
# 輔助函式：使用 API 快速建立測試資料
# ==========================================
@pytest.fixture(scope="function")
def api_context(playwright):
    """建立 API 請求上下文"""
    request_context = playwright.request.new_context(base_url="http://localhost:8000")
    yield request_context
    request_context.dispose()

def get_auth_token(api_request, email, password):
    """取得登入 Token"""
    # 使用 form= 參數傳送 application/x-www-form-urlencoded
    response = api_request.post("/auth/token", form={ 
        "username": email,
        "password": password
    })
    assert response.ok, f"API Login failed: {response.text()}"
    return response.json()["access_token"]

def setup_test_data(api_request):
    """
    準備資料：
    1. 雇主登入 -> 建立案件
    2. 工作者登入 -> 提交提案
    回傳: (project_id, proposal_id)
    """
    # 1. 雇主建立案件
    emp_token = get_auth_token(api_request, EMPLOYER_EMAIL, PASSWORD)
    project_title = f"Phase2 Test Project {uuid.uuid4().hex[:6]}"
    
    # 呼叫後端 API 建立案件 (略過 Skill Tag 以簡化)
    # 【修正】將 json 改為 data
    proj_res = api_request.post("/projects/", 
        headers={"Authorization": f"Bearer {emp_token}"},
        data={ 
            "title": project_title,
            "description": "API generated project for E2E testing.",
            "budget_min": 10000,
            "budget_max": 20000,
            "skill_tag_ids": [] 
        }
    )
    # 如果 API 強制需要標籤，這裡可能需要先 fetch tags，但在系統測試寬容度下通常可略
    # 若失敗，請確認後端是否允許空 skill_tag_ids
    assert proj_res.ok, f"Create Project failed: {proj_res.text()}"
    project_id = proj_res.json()["project_id"]

    # 2. 工作者提交提案
    free_token = get_auth_token(api_request, FREELANCER_EMAIL, PASSWORD)
    
    # 使用 multipart/form-data 上傳 (模擬檔案)
    # Playwright API 支援 multipart
    prop_res = api_request.post(f"/projects/{project_id}/proposals",
        headers={"Authorization": f"Bearer {free_token}"},
        multipart={
            "brief_description": "I am the best candidate via API.",
            "attachment": ("dummy.pdf", b"%PDF-1.4 dummy content", "application/pdf")
        }
    )
    assert prop_res.ok, f"Submit Proposal failed: {prop_res.text()}"
    
    print(f"✅ [Setup] 資料準備完成: Project {project_id}")
    return project_id, project_title

# ==========================================
# 測試主邏輯
# ==========================================

def login_user_ui(page: Page, base_url: str, email: str, pw: str):
    """UI 登入輔助函式"""
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(pw)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

def test_employer_accept_and_contract(browser: Browser, base_url: str, api_context):
    """
    ST-04-Phase2: 雇主接受提案 -> 合約生成 -> 通知檢查
    """
    # 1. [Arrange] 透過 API 準備好 "有一個提案的案件"
    project_id, project_title = setup_test_data(api_context)

    # 2. [Act] 雇主操作 UI
    context_emp = browser.new_context()
    page_emp = context_emp.new_page()
    
    # 2.1 登入
    login_user_ui(page_emp, base_url, EMPLOYER_EMAIL, PASSWORD)

    # 2.2 進入「提案管理頁面」
    # 路徑參照 router: /projects/:projectId/proposals
    target_url = f"{base_url}/projects/{project_id}/proposals"
    page_emp.goto(target_url)

    # 2.3 驗證看到提案卡片
    # 根據 ProposalManagementView.vue, 提案卡片 class="proposal-card"
    proposal_card = page_emp.locator(".proposal-card").first
    expect(proposal_card).to_be_visible()
    expect(proposal_card).to_contain_text("I am the best candidate via API")

    # 2.4 點擊「接受提案」
    # 根據 View, 按鈕文字是 "接受提案" (type="success")
    accept_btn = proposal_card.get_by_role("button", name="接受提案")
    accept_btn.click()

    # 2.5 處理確認對話框 (ElMessageBox)
    # Element Plus 的 Confirm Box 按鈕通常是 "確定" 或 "Confirm"
    # 我們等待 Dialog 出現並點擊確認
    confirm_btn = page_emp.locator(".el-message-box__btns .el-button--primary")
    expect(confirm_btn).to_be_visible()
    confirm_btn.click()

    # 2.6 [Assert] 驗證跳轉至合約頁面
    # 成功後會 router.push(`/contracts/${contractRes.data.contract_id}`)
    # 我們等待 URL 包含 /contracts/
    page_emp.wait_for_url(r"**/contracts/*")
    expect(page_emp).to_have_url(re.compile(r".*/contracts/.*"))
    
    # 驗證合約狀態為「協商中」
    # 根據 ContractView (假設), 會有狀態標籤
    expect(page_emp.locator("body")).to_contain_text("協商中")
    
    print("✅ [Employer] 提案已接受，合約已生成")
    context_emp.close()

    # ==========================================
    # 3. [Assert] 工作者檢查通知
    # ==========================================
    context_free = browser.new_context()
    page_free = context_free.new_page()

    # 3.1 登入工作者
    login_user_ui(page_free, base_url, FREELANCER_EMAIL, PASSWORD)

    # 3.2 檢查鈴鐺 (NotificationBell.vue)
    # 鈴鐺 class="bell-icon"
    bell_icon = page_free.locator(".bell-icon")
    expect(bell_icon).to_be_visible()

    # (選用) 檢查是否有紅點 (.is-dot) 或 has-unread class
    # expect(bell_icon).to_have_class(re.compile(r"has-unread")) 

    # 3.3 點擊鈴鐺打開列表
    page_free.locator(".notification-badge").click()

    # 3.4 驗證通知內容 (使用 Filter 彈性搜尋)
    # 我們不依賴 nth(0) 或 nth(1)，而是直接在列表中搜尋符合條件的通知
    
    # 定義所有通知項目
    all_notifications = page_free.locator(".notification-item")
    expect(all_notifications.first).to_be_visible()

    # 驗證 A: 是否有「合約建立」的通知
    # 條件：包含 "合約草案" 且 包含 專案標題
    contract_notif = all_notifications.filter(has_text="合約草案").filter(has_text=project_title)
    print("count:" + str(contract_notif.count()))
    print(contract_notif.all_text_contents())
    # 這裡如果不使用 nth(0)，filter 可能會回傳多個(如果跑多次)，我們只要確認至少有一個可見即可
    expect(contract_notif.first).to_be_visible()
    print("✅ 找到合約通知")

    # 驗證 B: 是否有「提案被接受」的通知
    # 條件：包含 "已被接受" 且 包含 專案標題
    accept_notif = all_notifications.filter(has_text="已被接受").filter(has_text=project_title)
    expect(accept_notif.first).to_be_visible()
    print("✅ 找到提案接受通知")

    print("✅ [Freelancer] 成功收到雙重通知 (順序不拘)")
    context_free.close()

import re # 用於正則表達式