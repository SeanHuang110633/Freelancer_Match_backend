# tests/stress/locust_stress_search.py
import csv
import random
import os
from locust import HttpUser, task, constant, events

# 全域變數儲存 Tokens
TOKENS = []

# 在 Locust 啟動時載入 Token 檔案
@events.init.add_listener
def _(environment, **kwargs):
    global TOKENS
    token_file = "tokens.csv"
    
    if not os.path.exists(token_file):
        print(f"❌ 錯誤: 找不到 {token_file}！請先執行 python generate_tokens.py")
        environment.runner.quit()
        return

    try:
        with open(token_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            TOKENS = [row[0] for row in reader if row]
        print(f"✅ 已載入 {len(TOKENS)} 個測試用 Token。")
    except Exception as e:
        print(f"❌ 讀取 CSV 失敗: {e}")
        environment.runner.quit()

class SearchStressUser(HttpUser):
    # 模擬真實使用者的思考時間 (1~3秒)
    # 這能更真實地模擬 Connection Pool 的佔用釋放頻率
    wait_time = constant(1) 
    
    access_token = None

    def on_start(self):
        if TOKENS:
            self.access_token = random.choice(TOKENS)
        else:
            self.stop() # 無 Token 則停止該 User

    @task
    def search_projects(self):
        """
        模擬複雜搜尋：同時篩選 地區 + 工作型態
        目標：測試 DB 在無快取狀態下的 I/O 與連線池極限
        """
        if not self.access_token: return

        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 參數隨機化，擴大資料庫掃描範圍
        # 註：雖然 seed_data 用的是 fake.city()，但使用模糊搜尋 (DB用 ILIKE %...%) 
        # 只要字串部分匹配就會觸發掃描，不一定要完全命中真實資料也能產生負載。
        locations = ["台北", "台中", "高雄", "新竹", "台南", "Remote", "US"]
        work_types = ["遠端", "實體", "混合"]
        
        location = random.choice(locations)
        work_type = random.choice(work_types)
        page = random.randint(1, 10) # 模擬翻頁，避免總是查第一頁

        # 呼叫 /projects/ 列表 API (對應 project_router.py)
        # 此 API 預設會進行 SQL 查詢
        self.client.get(
            f"/projects/?location={location}&work_type={work_type}&page={page}&size=20",
            headers=headers,
            name="/projects/search (Complex)"
        )