# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 資料庫設定
    DATABASE_URL: str
    # Redis URL
    REDIS_URL: str
    # JWT 設定
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240

    # --- 檔案儲存設定 ---
    FILE_STORAGE_MODE: str = "local"
    GCS_BUCKET_NAME: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # [已刪除] BACKEND_CORS_ORIGINS 相關的所有程式碼都不留
    # 我們改在 main.py 中手動處理，避免 Pydantic 因為格式錯誤而崩潰

    # --- 資料庫連線池設定 (新增) ---
    # 預設值設為 5 和 10 (SQLAlchemy 的標準預設值)
    # 這保證了 Cloud Run 上的行為與修改前完全一致，不會掛掉
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- Redis 連線池 (新增!) ---
    # 生產環境預設 20 (保守)，壓測時我們要在 docker-compose 覆寫它
    REDIS_POOL_SIZE: int = 20

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        # (關鍵) 告訴 Pydantic 忽略那些沒定義在 Model 裡的環境變數
        # 這樣即使 Cloud Run 傳入了 BACKEND_CORS_ORIGINS，Pydantic 也不會因為型別錯誤而報錯
        extra = "ignore"

# 建立設定實例
settings = Settings()