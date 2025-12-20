# tests/stress/generate_employer_tokens.py
import requests
import csv
import sys
import time

# 依據 seed_data.py 設定
# 雇主 ID 範圍：1 ~ 200
START_USER_ID = 1
END_USER_ID = 200

BASE_URL = "http://localhost:8000"
OUTPUT_FILE = "tokens_employer.csv" # 指定輸出檔案名稱
DEFAULT_PASSWORD = "1qaz2wsx"

def generate():
    print(f"🔄 [Employer] 開始為 User ID {START_USER_ID} ~ {END_USER_ID} 生成雇主 Token...")
    tokens = []
    success_count = 0
    fail_count = 0
    
    # 建立 Session 加快速度
    session = requests.Session()

    for i in range(START_USER_ID, END_USER_ID + 1):
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
                print(f"❌ 雇主 {email} 登入失敗: {resp.status_code} - {resp.text}")
                fail_count += 1
                
        except Exception as e:
            print(f"❌ 連線錯誤 ({email}): {e}")
            fail_count += 1

        # 進度條
        if i % 20 == 0:
            sys.stdout.write(f"\r⏳ 進度: {i}/{END_USER_ID} (成功: {success_count})")
            sys.stdout.flush()

    print(f"\n📊 雇主生成統計 - 成功: {success_count}, 失敗: {fail_count}")

    if tokens:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(tokens)
        print(f"✅ 雇主 Token 已寫入至 {OUTPUT_FILE}")
    else:
        print("⚠️ 未生成任何 Token，請檢查後端是否已啟動。")

if __name__ == "__main__":
    generate()