from playwright.sync_api import Page, Browser, expect
import uuid
import pytest

# 測試帳號（請確保這些帳號已在初始化資料中存在）
EMPLOYER_EMAIL = "e1@11.com"
PASSWORD = "1qaz2wsx"


@pytest.fixture(scope="function")
def api_context(playwright):
    request_context = playwright.request.new_context(base_url="http://localhost:8000")
    yield request_context
    request_context.dispose()


def get_token(api_request, email, password):
    res = api_request.post("/auth/token", form={"username": email, "password": password})
    assert res.ok, f"Login failed: {res.text()}"
    return res.json()["access_token"]


def setup_project_via_api(api_request):
    token = get_token(api_request, EMPLOYER_EMAIL, PASSWORD)
    title = f"MyJobs Test {uuid.uuid4().hex[:6]}"
    res = api_request.post(
        "/projects/",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "title": title,
            "description": "Project for my-jobs listing test",
            "budget_min": 1000,
            "budget_max": 2000,
            "skill_tag_ids": []
        },
    )
    assert res.ok, f"Create project failed: {res.text()}"
    project_id = res.json()["project_id"]
    return project_id, title


def login_ui(page: Page, base_url: str, email: str):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")


def test_employer_can_see_my_jobs_and_open_detail(browser: Browser, base_url: str, api_context):
    project_id, title = setup_project_via_api(api_context)

    context = browser.new_context()
    page = context.new_page()

    # 1. Employer login in UI
    login_ui(page, base_url, EMPLOYER_EMAIL)

    # 2. Go to My Jobs page (navbar / direct route)
    page.goto(f"{base_url}/my-jobs")

    # Ensure the project title appears in the list
    expect(page.locator(f'text="{title}"')).to_be_visible()

    # 3. Click the project card to view details
    # In the frontend the project card links to `/projects/{project.project_id}`
    # We click the link that contains the title
    page.get_by_text(title).click()

    # 4. Verify we navigated to the project detail page and title is shown
    page.wait_for_url(f"{base_url}/projects/{project_id}")
    expect(page.locator("h2")).to_contain_text(title)

    # 5. Optionally check employer email is visible in the details
    expect(page.locator(f'text={EMPLOYER_EMAIL}')).to_be_visible()

    context.close()
