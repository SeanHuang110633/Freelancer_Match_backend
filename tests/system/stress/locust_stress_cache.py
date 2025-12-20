import csv
import random
import os
import requests
from locust import HttpUser, task, constant, events

# 全域變數
TOKENS = []
TARGET_PROJECT_ID = None
BASE_URL = "http://localhost:8000"

def load_tokens():
    """讀取預先生成的 Token"""
    global TOKENS
    token_file = "tokens.csv"
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            TOKENS = [row[0] for row in reader if row]
        print(f"✅ [Init] 已載入 {len(TOKENS)} 個 Token。")
    else:
        print(f"❌ [Init] 找不到 {token_file}，請先執行 generate_tokens.py")
        exit(1)

def fetch_hot_project():
    """
    從 API 獲取一個真實的案件 ID 當作本次的『熱門案件』。
    這保證了我們測試的是存在的資料。
    """
    global TARGET_PROJECT_ID
    if not TOKENS:
        return

    # 使用第一個 token 來查詢
    token = TOKENS[0]
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # 隨便搜尋一個列表，取第一筆
        resp = requests.get(f"{BASE_URL}/projects/?size=1", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("items"):
                TARGET_PROJECT_ID = data["items"][0]["project_id"]
                print(f"🔥 [Init] 鎖定熱門案件 ID: {TARGET_PROJECT_ID}")
            else:
                print("⚠️ [Init] 搜尋結果為空，無法設定熱門案件。請檢查資料庫種子資料。")
                exit(1)
        else:
            print(f"❌ [Init] 初始化失敗，API 回傳: {resp.status_code}")
            exit(1)
    except Exception as e:
        print(f"❌ [Init] 連線錯誤: {e}")
        exit(1)

# Locust 啟動時執行一次初始化
@events.init.add_listener
def _(environment, **kwargs):
    load_tokens()
    fetch_hot_project()

class CacheStressUser(HttpUser):
    # 設定較短的等待時間，給予 Redis 更高壓力
    wait_time = constant(0.5) 
    
    access_token = None

    def on_start(self):
        if TOKENS:
            self.access_token = random.choice(TOKENS)
        else:
            self.stop()

    @task
    def view_hot_project(self):
        """
        模擬大量用戶讀取同一個『熱門案件詳情』
        預期：Redis Cache Hit
        """
        if not self.access_token or not TARGET_PROJECT_ID: 
            return

        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 呼叫單一案件詳情 API
        # 這應該會觸發 project_repo.get_project_view (含快取邏輯)
        self.client.get(
            f"/projects/{TARGET_PROJECT_ID}",
            headers=headers,
            name="/projects/{id} (Hot Cache)"
        )