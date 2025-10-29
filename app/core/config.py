# app/core/config.py
# 應用程式設定 (例如資料庫連線字串、JWT 秘鑰等)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 資料庫設定
    DATABASE_URL: str
    # JWT 設定
    JWT_SECRET_KEY: str
    # JWT 演算法
    JWT_ALGORITHM: str = "HS256"
    # 存取令牌過期時間（分鐘）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # 環境變數檔案 
    class Config:
        env_file = ".env"

# 建立設定實例
settings = Settings()