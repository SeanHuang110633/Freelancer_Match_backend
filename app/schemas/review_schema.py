# app/schemas/review_schema.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

# 基礎評分欄位 (數值範圍 0.0 - 5.0)
class ReviewBase(BaseModel):
    comment: Optional[str] = None

# 建立評價 (Input)
# 為了方便，我們將所有面向都列為 Optional，
# Service 層會根據 current_user 的角色來驗證 "必填" 的欄位群組。
class ReviewCreate(ReviewBase):
    contract_id: str
    
    # --- A. 雇主填寫 (評工作者) ---
    rating_communication_fw: Optional[float] = Field(None, ge=0, le=5)
    rating_professionalism_fw: Optional[float] = Field(None, ge=0, le=5)
    rating_punctuality_fw: Optional[float] = Field(None, ge=0, le=5)
    rating_quality_fw: Optional[float] = Field(None, ge=0, le=5)

    # --- B. 工作者填寫 (評雇主) ---
    rating_communication_we: Optional[float] = Field(None, ge=0, le=5)
    rating_quality_we: Optional[float] = Field(None, ge=0, le=5)
    rating_compensation_we: Optional[float] = Field(None, ge=0, le=5)
    rating_process_we: Optional[float] = Field(None, ge=0, le=5)

# 評價輸出 (Output)
class ReviewOut(ReviewBase):
    model_config = ConfigDict(from_attributes=True)

    review_id: str
    contract_id: str
    reviewer_id: str
    reviewee_id: str
    
    # 所有分數欄位
    rating_communication_fw: Optional[float] = None
    rating_professionalism_fw: Optional[float] = None
    rating_punctuality_fw: Optional[float] = None
    rating_quality_fw: Optional[float] = None

    rating_communication_we: Optional[float] = None
    rating_quality_we: Optional[float] = None
    rating_compensation_we: Optional[float] = None
    rating_process_we: Optional[float] = None

    created_at: datetime