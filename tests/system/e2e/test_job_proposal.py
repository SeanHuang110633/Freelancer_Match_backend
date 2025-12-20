import pytest
import uuid
from playwright.sync_api import Page, Browser, expect

# 真實測試帳號 (來自 back.sql)
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

@pytest.fixture
def dummy_pdf(tmp_path):
    """
    Fixture: 建立一個臨時的假 PDF 檔案，供提案上傳使用
    """
    pdf_path = tmp_path / "proposal.pdf"
    # PDF Header magic bytes
    pdf_path.write_bytes(b"%PDF-1.4\n%..." + b"0" * 100)
    return str(pdf_path)

def login_user(page: Page, base_url: str, email: str, pw: str):
    """輔助函式：快速登入"""
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(pw)
    page.get_by_role("button", name="Login").click()
    # 等待跳轉，確保登入完成
    page.wait_for_url(f"{base_url}/")

def test_job_posting_and_proposal(browser: Browser, base_url: str, dummy_pdf):
    """
    ST-04-Phase1: 雇主刊登案件 -> 工作者提案 -> 雇主收到通知
    驗證重點：
    1. 雇主成功建立案件，並取得 Project ID。
    2. 工作者能看到該案件詳情。
    3. 工作者能上傳 PDF 並提交提案。
    4. 系統正確顯示「你已提案」狀態。
    5. 【新增】雇主收到「收到新提案」的通知。
    """
    # ==========================================
    # 步驟 1: 雇主刊登案件 (Employer Context)
    # ==========================================
    context_emp = browser.new_context()
    page_emp = context_emp.new_page()
    
    # 1.1 登入
    login_user(page_emp, base_url, EMPLOYER_EMAIL, PASSWORD)

    # 1.2 進入刊登頁面
    page_emp.goto(f"{base_url}/post-job")

    # 1.3 填寫表單 (參照 JobCreateView.vue)
    job_title = f"System Test Project {uuid.uuid4().hex[:6]}"
    page_emp.get_by_placeholder("請輸入案件標題").fill(job_title)
    page_emp.get_by_placeholder("詳細說明案件需求、背景、交付標準等...").fill("This is an automated E2E test project.")
    
    # 填寫預算
    page_emp.locator(".el-input-number input").first.fill("50000")
    
    # 選擇技能 (勾選 Python)
    page_emp.locator("label").filter(has_text="Python").click()

    # 1.4 攔截 API 回應以獲取 Project ID
    with page_emp.expect_response("**/projects/") as response_info:
        page_emp.get_by_role("button", name="確認刊登").click()
    
    # 1.5 驗證刊登成功
    response = response_info.value
    assert response.ok, f"刊登 API 失敗: {response.status}"
    project_data = response.json()
    project_id = project_data["project_id"]
    print(f"✅ 案件已建立，ID: {project_id}")

    expect(page_emp.locator(".el-message--success")).to_contain_text("建立成功")

    # 關閉雇主視窗
    context_emp.close()

    # ==========================================
    # 步驟 2: 工作者提案 (Freelancer Context)
    # ==========================================
    context_free = browser.new_context()
    page_free = context_free.new_page()

    # 2.1 登入
    login_user(page_free, base_url, FREELANCER_EMAIL, PASSWORD)

    # 2.2 直接進入案件詳情頁
    target_url = f"{base_url}/projects/{project_id}"
    page_free.goto(target_url)

    # 2.3 驗證頁面內容
    expect(page_free.locator("h2").first).to_contain_text(job_title)

    # 2.4 點擊「我要提案」
    propose_btn = page_free.get_by_role("button", name="我要提案")
    expect(propose_btn).to_be_visible()
    propose_btn.click()

    # 2.5 填寫提案 Modal
    expect(page_free.locator(".el-dialog__title").filter(has_text="提交提案")).to_be_visible()
    page_free.get_by_placeholder("請輸入您的提案簡述...").fill("I am the best fit for this job.")

    # 上傳 PDF
    file_input = page_free.locator(".el-dialog input[type='file']")
    file_input.set_input_files(dummy_pdf)

    # 2.6 提交
    page_free.get_by_role("button", name="確認提交").click()

    # 2.7 驗證提案成功
    expect(page_free.locator(".el-message--success").filter(has_text="提案提交成功")).to_be_visible()

    # 2.8 驗證 UI 狀態改變
    success_tag = page_free.locator(".el-tag--success").filter(has_text="你已提案")
    expect(success_tag).to_be_visible()
    expect(page_free.get_by_role("button", name="我要提案")).not_to_be_visible()

    print("✅ 工作者提案成功")
    context_free.close()

    # ==========================================
    # 步驟 3: [新增] 雇主驗證通知 (Employer Context Check)
    # ==========================================
    context_emp_check = browser.new_context()
    page_emp_check = context_emp_check.new_page()

    # 3.1 雇主重新登入 (模擬收到通知後的行為)
    login_user(page_emp_check, base_url, EMPLOYER_EMAIL, PASSWORD)

    # 3.2 檢查鈴鐺 (NotificationBell.vue)
    bell_icon = page_emp_check.locator(".bell-icon")
    expect(bell_icon).to_be_visible()
    
    # 點擊打開列表
    page_emp_check.locator(".notification-badge").click()

    # 3.3 驗證通知內容
    # 根據 ProposalService，標題應為：案件「{project.title}」收到新提案
    all_notifications = page_emp_check.locator(".notification-item")
    expect(all_notifications.first).to_be_visible()

    # 使用 filter 尋找特定通知
    # 條件：包含 "收到新提案" 且 包含 專案標題
    proposal_notif = all_notifications.filter(has_text="收到新提案").filter(has_text=job_title)
    
    # 驗證該通知存在且可見
    expect(proposal_notif.first).to_be_visible()
    print(f"✅ 雇主成功收到提案通知: {proposal_notif.first.text_content()}")

    context_emp_check.close()