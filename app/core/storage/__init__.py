from app.core.config import settings
from app.core.storage.base import StorageProvider
from app.core.storage.local import LocalStorage
# 僅在需要時匯入 GCP，避免本地開發環境缺少套件報錯
# from app.core.storage.gcp import GCPStorage 

def get_storage_provider() -> StorageProvider:
    if settings.FILE_STORAGE_MODE == "gcs":
        from app.core.storage.gcp import GCPStorage
        return GCPStorage()
    else:
        return LocalStorage()