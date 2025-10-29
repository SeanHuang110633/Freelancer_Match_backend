# SE Project - Backend

## 專案結構說明

本專案採用 FastAPI (Python 3.11+), SQLAlchemy 2.0 (搭配 AsyncMySQL 驅動), Pydantic v2, Passlib, Python-JOSE (JWT) 等技術構建。目錄結構遵循分層架構設計，旨在實現關注點分離 (Separation of Concerns) 和高內聚低耦合。

```
freelancer_match_backend/
├── app/                    # FastAPI 應用程式核心程式碼
│   ├── core/               # 核心配置與基礎建設
│   │   ├── config.py       # Pydantic Settings，載入 .env 環境變數 (資料庫 URL, JWT 設定等)
│   │   ├── database.py     # SQLAlchemy 非同步引擎與 Session 設定，提供 get_db 依賴項
│   │   └── security.py     # 安全相關功能：密碼雜湊 (Bcrypt), JWT Token 產生/驗證, get_current_user 依賴項
│   ├── models/             # SQLAlchemy ORM 模型定義
│   │   ├── employer_profile.py # 雇主 Profile (`employer_profiles`) 資料表模型
│   │   ├── freelancer_profile.py # 自由工作者 Profile (`freelancer_profiles`) 資料表模型
│   │   ├── project.py      # 案件 (`projects`) 及案件技能關聯 (`project_skill_tags`) 資料表模型
│   │   ├── skill_tag.py    # 技能標籤 (`skill_tags`) 及工作者技能關聯 (`user_skill_tags`) 資料表模型
│   │   └── user.py         # 使用者 (`users`) 資料表模型
│   ├── repositories/       # 資料存取層 (Repository Pattern)：封裝 SQLAlchemy 查詢邏輯
│   │   ├── profile_repo.py # 處理 `freelancer_profiles` 和 `employer_profiles` 的 CRUD 及技能更新
│   │   ├── project_repo.py # 處理 `projects` 和 `project_skill_tags` 的 CRUD 及複合查詢
│   │   ├── skill_tag_repo.py # 處理 `skill_tags` 的查詢
│   │   └── user_repo.py    # 處理 `users` 的 CRUD
│   ├── routers/            # API 端點層 (Controllers)：定義 FastAPI 路由
│   │   ├── auth_router.py  # 身份驗證路由 (`/auth/register`, `/auth/token`)
│   │   ├── profile_router.py # Profile 相關路由 (`/profiles/me`, `/profiles/freelancer/skills`, etc.)
│   │   ├── project_router.py # 案件相關路由 (`/projects/`, `/projects/my`, `/projects/{id}`)
│   │   ├── recommendation_router.py # 推薦相關路由 (`/recommendations/jobs`, `/recommendations/freelancers`)
│   │   ├── skill_tag_router.py # 技能標籤路由 (`/tags/`)
│   │   └── user_router.py  # 使用者資訊路由 (`/users/me`)
│   ├── schemas/            # Pydantic 資料驗證模型 (用於 Request/Response Body)
│   │   ├── profile_schema.py # Profile 相關 API 的請求/回應格式定義 (含推薦 Schema)
│   │   ├── project_schema.py # 案件相關 API 的請求/回應格式定義 (含推薦 Schema)
│   │   ├── skill_tag_schema.py # 技能標籤 API 的回應格式定義
│   │   └── user_schema.py  # 使用者/認證 API 的請求/回應格式定義 (Login, Create, Out, Token)
│   ├── services/           # 業務邏輯層 (Service Layer)：協調 Repositories 處理複雜邏輯與權限控制
│   │   ├── auth_service.py # 註冊/登入業務邏輯
│   │   ├── profile_service.py # Profile 建立/更新/讀取業務邏輯
│   │   ├── project_service.py # 案件刊登/搜尋/讀取業務邏輯
│   │   ├── recommendation_service.py # 推薦業務邏輯 (調用 recommender)
│   │   └── skill_tag_service.py # 技能標籤讀取業務邏輯
│   └── utils/              # 共用工具函式
│       └── recommender.py  # 推薦演算法核心 (Levenshtein 相似度計算)
│   └── main.py             # FastAPI 應用程式入口，掛載 Middleware (CORS) 和 Routers
├── venv/                   # Python 虛擬環境
├── .env                    # 環境變數配置文件 (資料庫連線字串, JWT Secret 等)
├── .gitignore              # Git 忽略配置
├── README.md               # 專案說明文件
└── requirements.txt        # Python 依賴包列表
```

**架構說明：**

- **`main.py`:** 啟動點，整合各部分。
- **`core/`:** 應用程式的基礎設定，如資料庫連線、環境變數載入、安全性配置。
- **`models/`:** 定義資料庫表格的結構 (ORM)。
- **`schemas/`:** 定義 API 接口的資料格式 (輸入驗證、輸出序列化)。
- **`repositories/`:** 封裝與資料庫的直接互動 (SQLAlchemy 查詢)。
- **`services/`:** 包含核心業務邏輯，協調不同的 Repository 完成特定功能，並處理權限等問題。
- **`routers/`:** 定義 API 路徑 (`@app.get`, `@app.post` 等)，接收請求，呼叫 Service，回傳響應。
- **`utils/`:** 存放可重用的輔助工具或演算法。

這個結構有助於保持程式碼的組織性、可測試性和可維護性。

## technical stack

相關套件細節可以查看 requirements.txt 文件。

| 層級                    | 技術                                     | 功能說明                                                                                     |
| ----------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------- |
| **主框架**              | 🟢 **FastAPI**                           | 主體 Web Framework，提供 RESTful API 與 WebSocket 支援，支援 async/await，效能高、結構清晰。 |
| **語言**                | 🐍 **Python 3.11+**                      | 強型別、開發效率高、與 FastAPI 完美整合。                                                    |
| **伺服器**              | ⚡ **Uvicorn (ASGI)**                    | 非同步伺服器，啟動 FastAPI 應用，支援 WebSocket 高併發。                                     |
| **ORM 與資料層**        | 🧩 **SQLAlchemy 2.0**                    | ORM (Object-Relational Mapping)，將資料表映射為 Python 模型，支援非同步查詢。                |
| **資料庫**              | 🐘 **MySQL**                             | 主資料庫，儲存會員、案件、提案、合約、評價等核心業務資料。                                   |
| **快取與 Session 管理** | 🔴 **Redis**                             | 快取推薦結果、JWT Session、通知暫存，支援 pub/sub 通知推送。                                 |
| **資料驗證與序列化**    | 🧱 **Pydantic v2**                       | 定義請求與回應的 Schema（前後端資料交換格式）。                                              |
| **安全與驗證**          | 🔐 **python-jose + passlib + bcrypt**    | JWT Token 產生與驗證、密碼雜湊與比對。                                                       |
| **Mail 服務**           | 📧 **FastAPI-Mail**                      | 寄送密碼重設信與系統通知，支援 Jinja2 模板與 async 寄送。                                    |
| **推薦算法**            | 🧠 **python-Levenshtein**                | 技能標籤模糊比對與相似度計算，用於推薦自由工作者或案件。                                     |
| **背景任務與重試機制**  | 🕒 **tenacity**                          | 自動重試非同步任務（如發信、通知）。                                                         |
| **日誌管理**            | 📜 **Loguru**                            | 記錄請求、例外、審計日誌（Audit Logs），支援多層輸出與檔案輪替。                             |
| **設定管理**            | ⚙️ **python-dotenv**                     | 載入 `.env` 檔案中的環境變數（DB、Redis、JWT_SECRET 等）。                                   |
| **API 文件**            | 📘 **Swagger UI / Redoc (FastAPI 內建)** | 自動產生 API 文件與互動測試介面，可透過瀏覽器存取。                                          |
| **測試**                | 🧪 **pytest + pytest-asyncio + httpx**   | 單元測試與非同步 API 測試。                                                                  |
