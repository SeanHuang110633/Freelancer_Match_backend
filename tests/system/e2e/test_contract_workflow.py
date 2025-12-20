import pytest
import uuid
import re
from playwright.sync_api import Page, Browser, expect, APIRequestContext

# 真實測試帳號
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

# ==========================================
# API 輔助函式
# ==========================================
@pytest.fixture(scope="function")
def api_context(playwright):
    request_context = playwright.request.new_context(base_url="http://localhost:8000")
    yield request_context
    request_context.dispose()

@pytest.fixture
def dummy_file(tmp_path):
    f = tmp_path / "deliverable.zip"
    f.write_bytes(b"PK..." + b"0" * 100)
    return str(f)

def get_token(api_request, email, password):
    res = api_request.post("/auth/token", form={"username": email, "password": password})
    assert res.ok, f"Login failed: {res.text()}"
    return res.json()["access_token"]

def setup_contract_via_api(api_request):
    emp_token = get_token(api_request, EMPLOYER_EMAIL, PASSWORD)
    title = f"Contract Test {uuid.uuid4().hex[:6]}"
    
    proj_res = api_request.post("/projects/", headers={"Authorization": f"Bearer {emp_token}"}, data={
        "title": title, "description": "For contract testing", "budget_min": 10000, "budget_max": 20000, "skill_tag_ids": []
    })
    assert proj_res.ok
    project_id = proj_res.json()["project_id"]

    free_token = get_token(api_request, FREELANCER_EMAIL, PASSWORD)
    prop_res = api_request.post(f"/projects/{project_id}/proposals", headers={"Authorization": f"Bearer {free_token}"}, multipart={
        "brief_description": "I will do this.",
        "attachment": ("dummy.pdf", b"%PDF...", "application/pdf")
    })
    assert prop_res.ok
    proposal_id = prop_res.json()["proposal_id"]

    accept_res = api_request.patch(f"/proposals/{proposal_id}/status", headers={"Authorization": f"Bearer {emp_token}"}, data={"status": "已接受"})
    assert accept_res.ok
    
    contract_res = api_request.post("/contracts/", headers={"Authorization": f"Bearer {emp_token}"}, data={"proposal_id": proposal_id})
    assert contract_res.ok
    contract_id = contract_res.json()["contract_id"]

    print(f"✅ [Setup] 合約已建立: {contract_id}")
    return contract_id, title

def login_ui(page: Page, base_url: str, email: str):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

# ==========================================
# 劇本 A: Happy Path
# ==========================================
def test_contract_happy_path(browser: Browser, base_url: str, api_context, dummy_file):
    contract_id, title = setup_contract_via_api(api_context)
    
    context_emp = browser.new_context()
    context_free = browser.new_context()
    page_emp = context_emp.new_page()
    page_free = context_free.new_page()

    # 1. 簽署
    login_ui(page_free, base_url, FREELANCER_EMAIL)
    page_free.goto(f"{base_url}/contracts/{contract_id}")
    
    expect(page_free.locator("body")).to_contain_text("協商中")
    page_free.get_by_role("button", name="同意並開始").click()
    
    # 確認對話框
    expect(page_free.locator(".el-message-box")).to_be_visible()
    page_free.locator(".el-message-box__btns .el-button--primary").click()
    
    expect(page_free.locator("body")).to_contain_text("進行中")
    print("✅ 工作者已簽署")

    # 2. 上傳
    upload_btn = page_free.get_by_role("button", name="上傳")
    expect(upload_btn).to_be_visible()
    upload_btn.click()

    expect(page_free.locator(".el-dialog__title").filter(has_text="上傳交付物")).to_be_visible()
    page_free.get_by_placeholder("請描述此交付物內容...").fill("Here is the final work.")
    
    file_input = page_free.locator("input[type='file']")
    file_input.set_input_files(dummy_file)
    
    page_free.locator(".dialog-footer button").filter(has_text="上傳").click()
    expect(page_free.locator(".el-message--success").filter(has_text="交付物")).to_be_visible()
    expect(page_free.locator(".deliverables-list")).to_contain_text("Here is the final work")
    print("✅ 交付物已上傳")

    # 3. 請求驗收
    page_free.get_by_role("button", name="請求驗收").click()
    expect(page_free.locator(".el-message-box")).to_be_visible()
    page_free.locator(".el-message-box__btns .el-button--primary").click()
    
    # 驗證 tag (精準)
    expect(page_free.locator(".el-tag--warning").filter(has_text="工作者要求驗收")).to_be_visible()
    print("✅ 工作者已請求驗收")

    # 4. 驗證通過
    login_ui(page_emp, base_url, EMPLOYER_EMAIL)
    page_emp.goto(f"{base_url}/contracts/{contract_id}")
    
    expect(page_emp.locator(".el-tag--warning").filter(has_text="工作者要求驗收")).to_be_visible()
    
    page_emp.get_by_role("button", name="驗收通過").click()
    expect(page_emp.locator(".el-message-box")).to_be_visible()
    page_emp.locator(".el-message-box__btns .el-button--primary").click()

    # 驗證最終狀態 (精準) - 【修正點 1】
    expect(page_emp.locator(".el-tag--success").filter(has_text="已完成").first).to_be_visible()
    print("✅ 雇主驗收通過，合約已完成")

    context_emp.close()
    context_free.close()

# ==========================================
# 劇本 B: Termination Flow
# ==========================================
def test_contract_termination_flow(browser: Browser, base_url: str, api_context):
    contract_id, title = setup_contract_via_api(api_context)
    
    context_emp = browser.new_context()
    context_free = browser.new_context()
    page_emp = context_emp.new_page()
    page_free = context_free.new_page()

    # 1. 進入進行中
    login_ui(page_free, base_url, FREELANCER_EMAIL)
    page_free.goto(f"{base_url}/contracts/{contract_id}")
    page_free.get_by_role("button", name="同意並開始").click()
    page_free.locator(".el-message-box__btns .el-button--primary").click()
    expect(page_free.locator("body")).to_contain_text("進行中")

    # 2. 雇主請求終止
    login_ui(page_emp, base_url, EMPLOYER_EMAIL)
    page_emp.goto(f"{base_url}/contracts/{contract_id}")
    
    page_emp.get_by_role("button", name="請求終止").click()
    
    expect(page_emp.locator(".el-message-box")).to_be_visible()
    page_emp.locator(".el-message-box__btns .el-button--primary").click()
    
    # 驗證 tag (精準)
    expect(page_emp.locator(".el-tag--danger").filter(has_text="雇主請求終止")).to_be_visible()
    print("✅ 雇主已發出終止請求")

    # 3. 工作者同意終止
    page_free.reload()
    expect(page_free.locator(".el-tag--danger").filter(has_text="雇主請求終止")).to_be_visible()
    
    page_free.get_by_role("button", name="同意終止").click()
    
    expect(page_free.locator(".el-message-box")).to_be_visible()
    # 【修正點 2】直接點擊 primary button (確認按鈕)
    page_free.locator(".el-message-box__btns .el-button--primary").click()

    # 驗證最終狀態
    expect(page_free.locator(".el-tag--info").filter(has_text="合約已終止")).to_be_visible()
    print("✅ 工作者同意，合約已終止")

    context_emp.close()
    context_free.close()