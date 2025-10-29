import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    auth_router, user_router, 
    profile_router, skill_tag_router, 
    project_router, recommendation_router
)

# (新增) 設定基礎日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # 建立一個 logger 實例

app = FastAPI()

# --- 設定 CORS (跨來源資源共用) ---
# 允許所有來源 (在生產環境中應限制)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 允許所有來源 (或指定 'http://localhost:5173')
    allow_credentials=True,
    allow_methods=["*"], # 允許所有 HTTP 方法
    allow_headers=["*"], # 允許所有 HTTP 標頭
)

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