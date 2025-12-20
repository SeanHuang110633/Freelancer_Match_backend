import pytest
import uuid
import os
from playwright.sync_api import Page, expect

# 既有的真實帳號
FREELANCER_EMAIL = "w1@11.com"
PASSWORD = "1qaz2wsx"

@pytest.fixture
def dummy_image(tmp_path):
    """建立一個臨時的假圖片檔案"""
    img_path = tmp_path / "test_avatar.jpg"
    img_path.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 100)
    return str(img_path)

def login_user(page: Page, base_url: str, email: str, pw: str):
    """輔助函式"""
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(pw)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")

def test_employer_create_profile_with_upload(page: Page, base_url: str, dummy_image, playwright):
    """ST-03-A (Employer): 建立 Profile + 上傳 Logo"""
    # 1. 註冊新帳號
    new_email = f"emp_create_{uuid.uuid4().hex[:6]}@test.com"
    page.goto(f"{base_url}/login")
    page.get_by_text("Register right now").click()
    page.get_by_placeholder("Enter your Email").fill(new_email)
    page.get_by_placeholder("Enter password").first.fill(PASSWORD)
    page.get_by_placeholder("Re-enter your password").fill(PASSWORD)
    page.locator("label").filter(has_text="Employer").click()
    page.get_by_role("button", name="Register").click()
    
    expect(page.locator(".el-alert--success")).to_be_visible()
    page.get_by_text("Go to Login").click()
    
    # 2. 登入
    login_user(page, base_url, new_email, PASSWORD)

    # 3. 進入 Profile
    page.goto(f"{base_url}/profile")
    expect(page.locator("h2:has-text('Create Your Profile')")).to_be_visible()

    # 4. 填寫資料
    test_company = "AutoTest Corp."
    page.locator("input").first.fill(test_company)
    page.get_by_role("textbox", name="Company Bio").fill("We automate everything.")

    # 5. 上傳圖片
    upload_input = page.locator(".avatar-uploader input[type='file']").first
    upload_input.set_input_files(dummy_image)

    # 6. 【修正點】驗證上傳成功 (使用 filter 指定文字)
    # 這樣就算畫面上有多個 success message，也能精準抓到這一個
    expect(page.locator(".el-message--success").filter(has_text="Image uploaded successfully")).to_be_visible()
    
    expect(page.locator(".avatar-uploader .avatar")).to_be_visible()

    # 7. 提交
    page.get_by_role("button", name="Save and Get Started").click()

    # 8. 驗證建立成功
    expect(page.locator(".el-message--success").filter(has_text="Profile created successfully")).to_be_visible()
    
    # 9. (移除 page.reload()) 
    # 10. 直接驗證 Navbar，這次應該會自動更新了
    expect(page.locator(".navbar")).to_contain_text(test_company)

    # 11. 真實使用者流程：點擊 Navbar 的 Post Jobs，透過 UI 建立專案
    #     這確保前端載入標籤、提交表單並觸發推薦流程
    page.get_by_text("Post Jobs").click()
    page.wait_for_url(f"{base_url}/post-job")

    job_title = f"Employer Rec Job {uuid.uuid4().hex[:6]}"
    # 填寫標題與說明 (使用 JobCreateView 的 placeholder)
    page.get_by_placeholder("請輸入案件標題").fill(job_title)
    page.get_by_placeholder("詳細說明案件需求、背景、交付標準等...").fill("Seed job for recommendation via UI")

    # 等待技能標籤載入，若有則勾選第一個
    skill_checkbox = page.locator('.skill-checkbox').first
    if skill_checkbox.count() > 0:
        # 點選 checkbox（label 內文字）以勾選
        skill_checkbox.click()

    # 點擊確認刊登按鈕
    page.get_by_text("確認刊登").click()

    # 確認刊登成功訊息出現且包含標題
    expect(page.locator('.el-message--success')).to_contain_text(job_title)

    # 12. 回到首頁，系統應該提供推薦的工作者給雇主 (recommendation-card.freelancer-card)
    page.goto(f"{base_url}/")
    expect(page.locator('.recommendation-card.freelancer-card').first).to_be_visible(timeout=7000)


def test_freelancer_edit_profile_and_skills(page: Page, base_url: str):
    """ST-03-B & C (Freelancer): 編輯 Profile + 更新技能"""
    # 1. 登入
    login_user(page, base_url, FREELANCER_EMAIL, PASSWORD)
    page.goto(f"{base_url}/profile")

    # --- 場景 B: 編輯 ---
    # 判斷是進入了 Create 還是 Edit 模式 (視 w1@11.com 資料狀態而定)
    # 如果看到 "Create Your Profile"，代表該帳號還沒建立 Profile，我們這邊做個簡單的相容處理
    if page.locator("h2:has-text('Create Your Profile')").is_visible():
        # 如果是 Create 模式，先快速建立一個
        page.locator("input").first.fill("Freelancer W1")
        page.get_by_role("button", name="Save and Get Started").click()
        page.wait_for_timeout(1000) # 等待狀態切換

    # 點擊 Edit Profile (如果可見)
    edit_btn = page.get_by_role("button", name="Edit Profile")
    if edit_btn.is_visible():
        edit_btn.click()

    # 修改 Bio
    new_bio = f"Updated by Playwright {uuid.uuid4().hex[:4]}"
    page.locator("textarea").fill(new_bio)
    page.get_by_role("button", name="Save Changes").click()
    
    # 【修正點】驗證更新成功
    expect(page.locator(".el-message--success").filter(has_text="Basic info updated")).to_be_visible()
    expect(page.locator("textarea")).to_have_value(new_bio)

    # --- 場景 C: 技能 ---
    page.get_by_text("My Skills").click()

    # 勾選 Python
    python_checkbox = page.locator("label").filter(has_text="Python")
    # 等待元素載入
    expect(python_checkbox).to_be_visible() 
    python_checkbox.click()

    page.get_by_role("button", name="Update Skills").click()

    # 【修正點】驗證技能更新成功
    expect(page.locator(".el-message--success").filter(has_text="Skills updated successfully")).to_be_visible()

    # 4. 回到首頁，系統應該提供推薦的案件給自由工作者 (recommendation-card.job-card)
    page.goto(f"{base_url}/")
    # 使用 .first 避免 strict mode 錯誤（locator 可能匹配多個卡片）
    expect(page.locator('.recommendation-card.job-card').first).to_be_visible(timeout=5000)