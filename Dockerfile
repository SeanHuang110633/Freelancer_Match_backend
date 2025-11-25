# 使用官方 Python 輕量版映像檔
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 設定環境變數
# PYTHONDONTWRITEBYTECODE: 防止 Python 產生 .pyc 檔案
# PYTHONUNBUFFERED: 確保 Log 即時輸出 (對 Docker Log 很重要)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安裝系統依賴 (如果 asyncmy 或 crypto 需要編譯)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 複製專案程式碼 (注意 .dockerignore 會排除敏感檔案)
COPY . .

# Cloud Run 預設會注入 PORT 環境變數 (通常是 8080)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}