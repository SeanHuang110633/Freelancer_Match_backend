import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from app.core.storage.base import StorageProvider

# 設定專案根目錄與靜態檔案路徑
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent # 調整層級以指向專案根目錄
STATIC_DIR = BASE_DIR / "static" / "uploads"
URL_PREFIX = "/static/uploads"

class LocalStorage(StorageProvider):
    def __init__(self):
        os.makedirs(STATIC_DIR, exist_ok=True)

    async def save_file(self, file: UploadFile, directory: str) -> str:
        # 1. 準備目錄
        target_dir = STATIC_DIR / directory
        os.makedirs(target_dir, exist_ok=True)

        # 2. 生成檔名
        ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        file_path = target_dir / filename

        # 3. 寫入檔案
        try:
            content = await file.read()
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            # 游標重置，以免後續有其他操作需要
            await file.seek(0) 
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Local upload failed: {e}")

        # 4. 回傳相對路徑 URL
        return f"{URL_PREFIX}/{directory}/{filename}"

    async def delete_file(self, file_url: str) -> bool:
        # file_url 範例: /static/uploads/proposals/abc.pdf
        if not file_url.startswith(URL_PREFIX):
            return False
        
        relative_path = file_url.replace(URL_PREFIX, "").lstrip("/")
        file_path = STATIC_DIR / relative_path
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False