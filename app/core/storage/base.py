from abc import ABC, abstractmethod
from fastapi import UploadFile

class StorageProvider(ABC):
    """檔案儲存策略介面"""

    @abstractmethod
    async def save_file(self, file: UploadFile, directory: str) -> str:
        """儲存檔案並回傳可存取的 URL (或路徑)"""
        pass

    @abstractmethod
    async def delete_file(self, file_url: str) -> bool:
        """刪除檔案"""
        pass