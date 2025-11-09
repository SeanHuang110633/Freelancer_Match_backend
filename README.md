# SE Project - Backend

## 專案結構說明

本專案採用 FastAPI (Python 3.11+), SQLAlchemy 2.0 (搭配 AsyncMySQL 驅動), Pydantic v2, Passlib, Python-JOSE (JWT) 等技術構建。目錄結構遵循分層架構設計，旨在實現關注點分離 (Separation of Concerns) 和高內聚低耦合。

```
FREELANCER_MATCH_BACKEND/
├── app/
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── security.py
│   │
│   ├── models/
│   │   ├── contract.py
│   │   ├── employer_profile.py
│   │   ├── freelancer_profile.py
│   │   ├── message.py           # (M8.1 新增)
│   │   ├── notification.py      # (M8.3 新增)
│   │   ├── project.py
│   │   ├── proposal.py
│   │   ├── skill_tag.py
│   │   └── user.py
│   │
│   ├── repositories/
│   │   ├── contract_repo.py
│   │   ├── message_repo.py      # (M8.1 新增)
│   │   ├── notification_repo.py # (M8.3 新增)
│   │   ├── profile_repo.py
│   │   ├── project_repo.py
│   │   ├── proposal_repo.py
│   │   ├── skill_tag_repo.py
│   │   └── user_repo.py
│   │
│   ├── routers/
│   │   ├── auth_router.py
│   │   ├── contract_router.py
│   │   ├── message_router.py    # (M8.1 新增)
│   │   ├── notification_router.py # (M8.3 新增)
│   │   ├── profile_router.py
│   │   ├── project_router.py
│   │   ├── proposal_router.py
│   │   ├── recommendation_router.py
│   │   ├── skill_tag_router.py
│   │   └── user_router.py
│   │
│   ├── schemas/
│   │   ├── contract_schema.py
│   │   ├── message_schema.py    # (M8.1 新增)
│   │   ├── notification_schema.py # (M8.3 新增)
│   │   ├── profile_schema.py
│   │   ├── project_schema.py
│   │   ├── proposal_schema.py
│   │   ├── skill_tag_schema.py
│   │   └── user_schema.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── contract_service.py    # (M8.3 修改)
│   │   ├── message_service.py   # (M8.1 新增)
│   │   ├── notification_service.py # (M8.3 新增)
│   │   ├── profile_service.py
│   │   ├── project_service.py
│   │   ├── proposal_service.py    # (M8.3 修改)
│   │   ├── recommendation_service.py
│   │   └── skill_tag_service.py
│   │
│   ├── utils/
│   │   └── recommender.py
│   │
│   └── main.py                  # (M8.1/M8.3 修改)
│
├── static/
│   └── uploads/
│       └── proposals/
│
├── tests/
├── venv/
├── .env
├── .gitignore
└── README.md
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
