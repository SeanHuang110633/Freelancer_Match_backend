import uuid
import os
from fastapi import UploadFile, HTTPException, status
from google.cloud import storage
from app.core.storage.base import StorageProvider
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class GCPStorage(StorageProvider):
    def __init__(self):
        try:
            self.client = storage.Client()
            self.bucket_name = settings.GCS_BUCKET_NAME
            if not self.bucket_name:
                raise ValueError("GCS_BUCKET_NAME not set")
            self.bucket = self.client.bucket(self.bucket_name)
        except Exception as e:
            logger.error(f"GCS Init failed: {e}")
            raise

    async def save_file(self, file: UploadFile, directory: str) -> str:
        try:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            blob_path = f"{directory}/{filename}"
            
            blob = self.bucket.blob(blob_path)
            content = await file.read()
            
            # GCS Python Client 是同步的，但在 FastAPI async路徑中，
            # 對於 I/O bound 操作，若無原生 async 庫，直接呼叫通常可接受，
            # 或使用 run_in_threadpool 優化。此處為求簡潔直接呼叫。
            blob.upload_from_string(content, content_type=file.content_type)
            blob.make_public()
            
            await file.seek(0)
            return blob.public_url
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"GCS upload failed: {e}")

    async def delete_file(self, file_url: str) -> bool:
        # file_url 範例: https://storage.googleapis.com/BUCKET_NAME/proposals/abc.pdf
        prefix = f"https://storage.googleapis.com/{self.bucket_name}/"
        if not file_url.startswith(prefix):
            return False
        
        blob_name = file_url.replace(prefix, "")
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            return True
        return False