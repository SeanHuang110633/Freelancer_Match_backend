import csv
import random
import os
from locust import HttpUser, task, constant, events

# 全域變數儲存 Tokens
TOKENS = []
# 使用自由工作者的 Token (計算量較大：匹配 5000 筆案件)
TOKEN_FILE = "tokens.csv"

# 1. 啟動時載入 Token
@events.init.add_listener
def _(environment, **kwargs):
    global TOKENS
    
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ 錯誤: 找不到 {TOKEN_FILE}！")
        print("💡 請先執行: python generate_tokens.py")
        environment.runner.quit()
        return

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            TOKENS = [row[0] for row in reader if row]
        print(f"✅ [Test 5] 已載入 {len(TOKENS)} 個自由工作者 Token。")
    except Exception as e:
        print(f"❌ 讀取 CSV 失敗: {e}")
        environment.runner.quit()

class RecommendationStressUser(HttpUser):
    # 設定等待時間為 1 秒，模擬用戶瀏覽推薦列表後的思考
    wait_time = constant(1)
    
    access_token = None

    def on_start(self):
        if TOKENS:
            self.access_token = random.choice(TOKENS)
        else:
            self.stop()

    @task
    def get_recommendations(self):
        """
        請求推薦案件列表
        - 冷啟動時：觸發後端 Levenshtein 演算法 (CPU 密集)
        - 熱啟動時：直接讀取 Redis (App CPU 密集 - 序列化)
        """
        if not self.access_token: return

        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 參數說明：
        # limit=10: 雖然只取 10 筆，但在無快取時，後端通常需要計算所有候選者分數才能排序
        # 這確保了我們測試的是演算法的完整負載
        self.client.get(
            "/recommendations/jobs?limit=10&offset=0",
            headers=headers, 
            name="/recommendations/jobs (Algo)"
        )