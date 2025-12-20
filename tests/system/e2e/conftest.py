# tests/system/e2e/conftest.py
import pytest

# 設定 Playwright 的預設行為
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        # 設定視窗大小，避免響應式佈局隱藏某些元素
        "viewport": {"width": 1280, "height": 720},
        # 忽略 HTTPS 錯誤 (如果是本地測試)
        "ignore_https_errors": True,
    }

@pytest.fixture(scope="session")
def base_url():
    # 指向 Docker 啟動的前端位址
    return "http://localhost:8080"