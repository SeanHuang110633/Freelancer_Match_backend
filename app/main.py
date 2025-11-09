import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    auth_router, user_router, 
    profile_router, skill_tag_router, 
    project_router, recommendation_router, contract_router
)

# 單獨匯入 "proposal_router.py" 檔案中的 *兩個* router
from app.routers.proposal_router import (
    router as proposal_main_router,  # 將 router 重新命名
    project_proposal_router as proposal_project_router # 將 project_proposal_router 重新命名
)

# (M8.3 新增)
from app.routers import notification_router
# (M8.1 新增)
from app.routers import message_router

# --- 匯入所有 Model 檔案 ---
# 都在應用程式啟動時被 SQLAlchemy 註冊。
from app.models import user
from app.models import employer_profile
from app.models import freelancer_profile
from app.models import skill_tag
from app.models import project
from app.models import proposal
from app.models import contract
from app.models import notification
from app.models import message



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
app.include_router(proposal_main_router)
app.include_router(proposal_project_router)
app.include_router(contract_router.router)
app.include_router(notification_router.router)
app.include_router(message_router.router)
