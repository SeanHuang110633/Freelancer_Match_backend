import pytest
import json
import re
from playwright.sync_api import Page, Browser, expect

# Existing test accounts
FREELANCER_EMAIL = "w1@11.com"
EMPLOYER_EMAIL = "e1@11.com"
PASSWORD = "1qaz2wsx"

# --- 設定：是否使用模擬資料 (Mock) ---
USE_MOCK_API = True 

def login_ui(page: Page, base_url: str, email: str, pw: str = PASSWORD):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(pw)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

# --- Mock Helper Functions (修正與優化) ---
def mock_search_jobs_api(page: Page):
    # Mock Tags
    page.route("**/tags", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps([{"tag_id": "tag_999", "name": "Figma", "category": "Dev"}])
    ))
    # Mock Search Projects (使用正則以匹配 query params)
    page.route(re.compile(r".*/projects/.*"), lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps([{
            "project_id": "proj_101",
            "title": "Mocked Python Project",
            "description": "This is a mocked project for UI testing.",
            "budget_min": 1000,
            "budget_max": 5000,
            "location": "Taipei Mock",
            "work_type": "遠端",
            "skills": [{"tag": {"tag_id": "tag_999", "name": "Figma"}}]
        }])
    ))
    # Mock Project Detail
    page.route(re.compile(r".*/projects/proj_101$"), lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "project_id": "proj_101",
            "title": "Mocked Python Project",
            "description": "This is a mocked project for UI testing.",
            "budget_min": 1000,
            "budget_max": 5000,
            "location": "Taipei Mock",
            "work_type": "遠端",
            "skills": [{"tag": {"tag_id": "tag_999", "name": "Figma"}}]
        })
    ))

def mock_freelancer_search_api(page: Page):
    # Mock Tags
    page.route("**/tags", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps([{"tag_id": "tag_888", "name": "Adobe XD", "category": "Design"}])
    ))
    # Mock Search Freelancers
    # 注意：這裡使用正則確保能匹配帶參數的 URL
    page.route(re.compile(r".*/profiles/freelancers/search.*"), lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps([{
            "profile_id": "prof_202",
            "user_id": "user_50",
            "full_name": "Mock Designer",
            "skills": [{"tag": {"tag_id": "tag_888", "name": "Adobe XD"}}], # 符合前端結構
            "avatar_url": None,
            "reputation_score": 5.0,
            "visibility": "公開"
        }])
    ))
    # Mock Freelancer Detail
    # API: /profiles/freelancer/{id} (單數)
    page.route(re.compile(r".*/profiles/freelancer/user_50$"), lambda route: route.fulfill( 
        status=200,
        content_type="application/json",
        body=json.dumps({
            "user_id": "user_50",
            "profile_id": "prof_202",
            "full_name": "Mock Designer",
            "bio": "Experienced designer.",
            "phone": "0912345678",
            "avatar_url": None,
            "visibility": "公開",
            "reputation_score": 5.0,
            # [重要修正]: 結構必須是 skills -> [{ tag: { name: ... } }]
            "skills": [{"tag": {"tag_id": "tag_888", "name": "Adobe XD"}, "familiarity_level": 5}]
        })
    ))

# ================= 測試案例 1: 搜尋案件 (修復下拉選單) =================
def test_freelancer_search_jobs_by_skill_and_work_type(browser: Browser, base_url: str):
    context = browser.new_context()
    page = context.new_page()

    if USE_MOCK_API:
        print("\n[INFO] Using MOCKED API data for testing UI.")
        mock_search_jobs_api(page)
        target_data = ("tag_999", "Figma", "遠端", {"title": "Mocked Python Project"})
    else:
        pytest.skip("此測試目前僅支援 Mock 模式驗證 UI")

    login_ui(page, base_url, FREELANCER_EMAIL)

    page.goto(f"{base_url}/find-jobs")
    # 確保頁面載入完成
    expect(page.locator("h2", has_text="搜尋案件")).to_be_visible()

    tag_id, tag_name, work_type, project = target_data

    # --- 1. 工作型態 (Single Select) ---
    print(f"[ACTION] Clicking Work Type Select for {work_type}...")
    work_type_select = page.locator("div.el-form-item", has_text="工作型態").locator(".el-select__wrapper")
    work_type_select.click()
    
    # 選取選項
    dropdown_item = page.locator(".el-select-dropdown__item:visible").get_by_text(work_type, exact=True)
    dropdown_item.click()

    # 【關鍵修正 1】: 加入短暫等待，讓前一個下拉選單完全收起，避免 DOM 干擾
    page.wait_for_timeout(500)

    # --- 2. 技能 (Multi Select) ---
    print(f"[ACTION] Clicking Skill Select for {tag_name}...")
    skill_select = page.locator("div.el-form-item", has_text="技能").locator(".el-select__wrapper")
    skill_select.click()
    
    # 等待下拉選單出現
    skill_option = page.locator(".el-select-dropdown__item:visible").filter(has_text=tag_name).first
    expect(skill_option).to_be_visible()
    skill_option.click()
    
    # 點擊空白處收起選單
    print("[ACTION] Closing dropdown...")
    page.locator("h2", has_text="搜尋案件").click()
    page.wait_for_timeout(300) # 等待選單收起動畫

    # --- 3. 搜尋 ---
    page.get_by_role("button", name="Search").click()

    # --- 驗證 ---
    # 等待專案卡片出現 (確保 Mock API 回傳被處理)
    card = page.locator('.project-card').first
    expect(card).to_be_visible(timeout=5000)
    
    # 點擊進入詳情
    card.click()
    
    # 驗證詳情頁
    expect(page.locator('h2')).to_contain_text(project.get('title'))

    context.close()


# ================= 測試案例 2: 搜尋人才 (修復 Profile 顯示) =================
def test_employer_search_freelancers_by_skill_and_open_detail(browser: Browser, base_url: str):
    context = browser.new_context()
    page = context.new_page()

    if USE_MOCK_API:
        print("\n[INFO] Using MOCKED API data for testing UI.")
        mock_freelancer_search_api(page)
        target_data = ("tag_888", "Adobe XD", {"real_name": "Mock Designer"})
    else:
        pytest.skip("此測試目前僅支援 Mock 模式驗證 UI")

    login_ui(page, base_url, EMPLOYER_EMAIL)

    page.goto(f"{base_url}/find-freelancers")
    expect(page.locator("h2", has_text="Search Freelancers")).to_be_visible()

    tag_id, tag_name, profile = target_data
    
    # --- 1. 技能 (Multi Select) ---
    print(f"[ACTION] Clicking Skill Select for {tag_name}...")
    skill_select = page.locator("div.el-form-item", has_text="Skills").locator(".el-select__wrapper")
    skill_select.click()
    
    # 等待下拉選單
    skill_option = page.locator(".el-select-dropdown__item:visible").filter(has_text=tag_name).first
    expect(skill_option).to_be_visible()
    skill_option.click()
    
    # 收起選單
    page.locator("h2", has_text="Search Freelancers").click()
    page.wait_for_timeout(300)

    # --- 2. 搜尋 ---
    page.get_by_role("button", name="Search").click()

    # --- 驗證 ---
    card = page.locator('.freelancer-col').first
    expect(card).to_be_visible(timeout=5000)

    # 點擊進入詳情
    # 【關鍵修正 2】: 確保等待 API 回應，避免頁面因資料未載入而空白
    with page.expect_response(re.compile(r".*/profiles/freelancer/user_50$")):
        card.click()
    
    # 驗證詳情頁資料
    expect(page.locator('.profile-name')).to_contain_text("Mock Designer")

    context.close()