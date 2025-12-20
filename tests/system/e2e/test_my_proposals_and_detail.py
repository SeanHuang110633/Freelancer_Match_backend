from playwright.sync_api import Page, Browser, expect
import uuid
import pytest

# 測試帳號（請確保這些帳號已在初始化資料中存在）
EMPLOYER_EMAIL = "e1@11.com"
FREELANCER_EMAIL = "w1@11.com"
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


def setup_project_and_proposal(api_request):
    # employer creates a project
    emp_token = get_token(api_request, EMPLOYER_EMAIL, PASSWORD)
    title = f"MyProposals Test {uuid.uuid4().hex[:6]}"
    proj_res = api_request.post(
        "/projects/",
        headers={"Authorization": f"Bearer {emp_token}"},
        data={
            "title": title,
            "description": "Project for my-proposals listing test",
            "budget_min": 500,
            "budget_max": 1500,
            "skill_tag_ids": [],
        },
    )
    assert proj_res.ok, f"Create project failed: {proj_res.text()}"
    project_id = proj_res.json()["project_id"]

    # freelancer submits a proposal for the project
    free_token = get_token(api_request, FREELANCER_EMAIL, PASSWORD)
    prop_res = api_request.post(
        f"/projects/{project_id}/proposals",
        headers={"Authorization": f"Bearer {free_token}"},
        multipart={
            "brief_description": "I will do this job.",
            # small dummy file
            "attachment": ("dummy.pdf", b"%PDF-1.4...", "application/pdf"),
        },
    )
    assert prop_res.ok, f"Create proposal failed: {prop_res.text()}"
    proposal_id = prop_res.json()["proposal_id"]

    return project_id, proposal_id, title


def login_ui(page: Page, base_url: str, email: str, password: str = PASSWORD):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("Enter your Email").fill(email)
    page.get_by_placeholder("Enter your password").fill(password)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url(f"{base_url}/")


def test_freelancer_my_proposals_and_open_detail(browser: Browser, base_url: str, api_context):
    project_id, proposal_id, project_title = setup_project_and_proposal(api_context)

    context = browser.new_context()
    page = context.new_page()

    # 1. Freelancer login in UI
    login_ui(page, base_url, FREELANCER_EMAIL)

    # 2. Go to My Proposals page
    page.goto(f"{base_url}/my-proposals")

    # Ensure the proposal (project title) appears in the list
    expect(page.locator(f'text="{project_title}"')).to_be_visible()

    # 3. Click the proposal card (the router-link wraps the card)
    page.get_by_text(project_title).click()

    # 4. Verify navigation to the proposal detail page
    page.wait_for_url(f"{base_url}/my-proposals/{proposal_id}")

    # 5. Verify the proposal detail shows the project title
    expect(page.locator(f'text="{project_title}"')).to_be_visible()

    context.close()
