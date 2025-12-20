import random
from locust import HttpUser, task, constant

# 統一密碼 (對應 seed_data.py)
TEST_USER_PASSWORD = "1qaz2wsx"

class AuthStressUser(HttpUser):
    # 維持每秒 1 次請求，這是非常高壓的設定 (Hardcore Mode)
    # 這非常適合用來驗證我們剛做的 ThreadPool 優化是否有顯著效果
    wait_time = constant(1)
    
    @task
    def login_storm(self):
        user_id = random.randint(1, 1000)
        email = f"stress_user_{user_id}@test.com"
        
        # 發送登入請求
        with self.client.post(
            "/auth/token",
            data={
                "username": email,
                "password": TEST_USER_PASSWORD
            },
            name="/auth/token (Login Storm)",
            catch_response=True,
            timeout=10  # 【建議新增】設定 10 秒逾時，避免 Locust Client 卡死
        ) as response:
            
            # 成功取得 Token (200 OK)
            if response.status_code == 200:
                response.success()
                
            # 伺服器過載 (500 系列錯誤)
            elif response.status_code >= 500:
                response.failure(f"Server Overloaded: {response.status_code}")
                
            # 請求逾時 (Locust 主動斷開或 Client 端斷線)
            # 當 response.status_code 為 0 時，通常代表 timeout 或連線被重置
            elif response.status_code == 0:
                response.failure("Timeout: Response took too long")
                
            # 登入失敗 (401/422) - 驗證失敗
            else:
                response.failure(f"Login Failed: {response.status_code} - {response.text[:100]}")