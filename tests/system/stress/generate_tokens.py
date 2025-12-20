# tests/stress/generate_tokens.py
import requests
import csv
import sys
import time

# 設定目標：針對種子資料中的「自由工作者」生成 Token
# seed_data.py: 自由工作者 ID 範圍為 201 ~ 1000
START_USER_ID = 201
END_USER_ID = 1000
BASE_URL = "http://localhost:8000" # 確保打到 Nginx 入口
OUTPUT_FILE = "tokens.csv"
DEFAULT_PASSWORD = "1qaz2wsx"

def generate():
    print(f"🔄 開始為 User ID {START_USER_ID} ~ {END_USER_ID} 生成 Token...")
    tokens = []
    success_count = 0
    fail_count = 0
    
    # 建立 Session 以重複利用 TCP 連線，加快生成速度
    session = requests.Session()

    for i in range(START_USER_ID, END_USER_ID + 1):
        # 根據 seed_data.py 的格式
        email = f"stress_user_{i}@test.com"
        
        try:
            # 呼叫登入 API
            resp = session.post(f"{BASE_URL}/auth/token", data={
                "username": email,
                "password": DEFAULT_PASSWORD
            })
            
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                tokens.append([token])
                success_count += 1
            else:
                print(f"❌ User {email} 登入失敗: {resp.status_code} - {resp.text}")
                fail_count += 1
                
        except Exception as e:
            print(f"❌ 連線錯誤 ({email}): {e}")
            fail_count += 1

        # 進度條顯示
        if i % 50 == 0:
            sys.stdout.write(f"\r⏳ 進度: {i}/{END_USER_ID} (成功: {success_count})")
            sys.stdout.flush()

    print(f"\n📊 生成統計 - 成功: {success_count}, 失敗: {fail_count}")

    if tokens:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(tokens)
        print(f"✅ Token 已寫入至 {OUTPUT_FILE}")
    else:
        print("⚠️ 未生成任何 Token，請檢查後端是否已啟動或資料庫是否已播種。")

if __name__ == "__main__":
    generate()