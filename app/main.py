# app/main.py
import logging
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.redis import redis_manager

# 匯入 Routers
from app.routers import (
    auth_router, user_router, 
    profile_router, skill_tag_router, 
    project_router, recommendation_router, contract_router, deliverable_router, review_router,
    notification_router, message_router
)

# 單獨匯入 "proposal_router.py" 檔案中的 router
from app.routers.proposal_router import (
    router as proposal_main_router,
    project_proposal_router as proposal_project_router
)

# --- 匯入所有 Model (讓 SQLAlchemy 註冊) ---
from app.models import (
    user, employer_profile, freelancer_profile, skill_tag,
    project, proposal, contract, notification, message,
    deliverable, review
)

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Lifespan 事件處理 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === 應用程式啟動時 ===
    logger.info("系統啟動中...")
    
    # 1. 初始化 Redis 連線池
    redis_manager.initialize()
    
    logger.info("系統啟動完成。")
    yield
    # === 應用程式關閉時 ===
    logger.info("系統關閉中...")
    
    # 1. 關閉 Redis 連線
    await redis_manager.close()
    
    logger.info("系統關閉完成。")

# 建立 FastAPI 實例
app = FastAPI(
    title="接案平台 API",
    version="1.0.0",
    lifespan=lifespan
)

# --- (關鍵修改) 手動處理 CORS 設定 ---
# 目的：繞過 Pydantic 的嚴格檢查，防止因環境變數格式錯誤導致啟動崩潰

def get_cors_origins():
    # 1. 從環境變數讀取原始字串，預設值為 "*" (開放所有)
    raw_cors = os.getenv("BACKEND_CORS_ORIGINS", "*")
    
    # 去除前後空白
    raw_cors = raw_cors.strip()

    # 2. 容錯解析邏輯
    try:
        if raw_cors == "*":
            return ["*"]
        
        # 如果看起來像 JSON 陣列 (例如 ["http://localhost"])
        if raw_cors.startswith("["):
            return json.loads(raw_cors)
        
        # 如果是逗號分隔的字串 (例如 http://a.com,http://b.com)
        return [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
        
    except Exception as e:
        logger.error(f"CORS 環境變數解析失敗: {e}，將回退至允許所有來源 (*)。Raw value: {raw_cors}")
        return ["*"]

# 執行解析
allow_origins_list = get_cors_origins()
logger.info(f"CORS Allowed Origins: {allow_origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_list, # 使用我們手動解析的列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- (CORS 設定結束) ---


# --- 靜態檔案掛載 ---
if settings.FILE_STORAGE_MODE == "local":
    static_dir = "static"
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        logger.info(f"已建立靜態資料夾: {static_dir}")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"已掛載本地靜態檔案目錄 (Local Mode): {static_dir}")
else:
    logger.info(f"檔案儲存模式為 GCS，不掛載本地 /static 目錄。")


# --- 根路徑 ---
@app.get("/")
def read_root():
    return {"status": "success", "message": "Backend is running!"}

# --- 載入 API 路由 ---
app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(profile_router.router)
app.include_router(skill_tag_router.router)
app.include_router(project_router.router)
app.include_router(recommendation_router.router)
app.include_router(proposal_main_router)
app.include_router(proposal_project_router)
app.include_router(contract_router.router)
app.include_router(notification_router.router)
app.include_router(message_router.router)
app.include_router(deliverable_router.router)
app.include_router(review_router.router)