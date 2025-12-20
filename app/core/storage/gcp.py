import uuid
import os
import logging
from urllib.parse import urlparse, unquote

from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool  # (新增) 用於非阻塞上傳
from google.cloud import storage

from app.core.storage.base import StorageProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class GCPStorage(StorageProvider):
    def __init__(self):
        try:
            self.client = storage.Client()
            self.bucket_name = settings.GCS_BUCKET_NAME
            if not self.bucket_name:
                raise ValueError("GCS_BUCKET_NAME not set")
            
            self.bucket = self.client.bucket(self.bucket_name)

            # 【新增】模擬器專用邏輯：自動建立 Bucket
            # 此邏輯只會在偵測到 STORAGE_EMULATOR_HOST 時執行，絕對不會影響生產環境
            if os.getenv("STORAGE_EMULATOR_HOST"):
                try:
                    if not self.bucket.exists():
                        self.bucket.create()
                        logger.info(f"[GCS Emulator] Automatically created bucket: {self.bucket_name}")
                except Exception as e:
                    # 模擬器連線失敗不應導致整個 App 崩潰，印出警告即可
                    logger.warning(f"[GCS Emulator] Failed to ensure bucket exists: {e}")

        except Exception as e:
            logger.error(f"GCS Init failed: {e}")
            raise

    async def save_file(self, file: UploadFile, directory: str) -> str:
        try:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            blob_path = f"{directory}/{filename}"
            
            blob = self.bucket.blob(blob_path)
            
            # 先讀取內容
            content = await file.read()
            
            # 【關鍵修改】定義同步上傳函式
            def _sync_upload():
                # GCS 上傳是同步 IO，必須封裝
                blob.upload_from_string(content, content_type=file.content_type)
                blob.make_public()
                return blob.public_url

            # 【關鍵修改】將同步操作丟入 ThreadPool，避免阻塞 Async Event Loop
            # 這對生產環境的高併發也是有益的優化
            public_url = await run_in_threadpool(_sync_upload)
            
            # 重置指標，以防後續還有其他操作需要讀取 file
            await file.seek(0)
            
            return public_url

        except Exception as e:
            logger.error(f"GCS upload failed: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File upload failed")

    async def delete_file(self, file_url: str) -> bool:
        """
        刪除檔案。支援生產環境 URL 與 模擬器 URL 解析。
        """
        if not file_url:
            return False

        try:
            # 解析 URL 取得路徑
            parsed = urlparse(file_url)
            path = unquote(parsed.path) # 解碼 (處理空格或特殊字元)

            # 邏輯 A: 生產環境 (storage.googleapis.com)
            # URL 結構通常是: /BUCKET_NAME/folder/filename.ext
            if "storage.googleapis.com" in file_url:
                prefix = f"/{self.bucket_name}/"
                if path.startswith(prefix):
                    blob_name = path.replace(prefix, "", 1)
                else:
                    # 如果格式對不上，視為無效
                    return False

            # 邏輯 B: 模擬器環境 (fake-gcs-server)
            # URL 結構可能是: /storage/v1/b/BUCKET_NAME/o/folder%2Ffilename.ext
            # 或者直接是: /BUCKET_NAME/folder/filename.ext (視模擬器版本而定)
            elif os.getenv("STORAGE_EMULATOR_HOST"):
                # 簡單策略：嘗試從路徑中移除 Bucket Name 之前的部分
                # 我們假設 blob_name 是路徑中 "bucket_name/" 之後的所有內容
                if self.bucket_name in path:
                    # 分割路徑，取 bucket_name 之後的部分
                    parts = path.split(f"/{self.bucket_name}/")
                    if len(parts) > 1:
                        blob_name = parts[1]
                    else:
                        return False
                else:
                    return False
            
            # 邏輯 C: 其他不認識的 URL
            else:
                return False

            # 執行刪除 (同樣建議丟入 ThreadPool，雖非必須但較安全)
            blob = self.bucket.blob(blob_name)
            
            def _sync_delete():
                if blob.exists():
                    blob.delete()
                    return True
                return False

            return await run_in_threadpool(_sync_delete)

        except Exception as e:
            logger.error(f"GCS delete failed for {file_url}: {e}")
            return False