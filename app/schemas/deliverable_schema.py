# app/schemas/deliverable_schema.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# 基礎欄位
class DeliverableBase(BaseModel):
    description: Optional[str] = None

# 建立時 (Input)
# 注意：檔案上傳主要透過 UploadFile (Form Data)，
# description 可以是 Form 欄位，這裡定義 Schema 主要用於驗證非檔案欄位。
class DeliverableCreate(DeliverableBase):
    pass 

# 回傳時 (Output)
class DeliverableOut(DeliverableBase):
    model_config = ConfigDict(from_attributes=True)

    deliverable_id: str
    contract_id: str
    uploader_id: str
    file_url: Optional[str] = None
    acceptance_status: str
    created_at: datetime