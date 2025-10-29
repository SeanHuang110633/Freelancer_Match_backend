from pydantic import BaseModel, EmailStr, Field, field_validator
import re
from app.models.user import UserRoleEnum

# 登入請求的格式
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Token 回應的格式
class Token(BaseModel):
    access_token: str
    token_type: str

# (可選) Token 內的資料
class TokenData(BaseModel):
    user_id: str
    role: str


# 1. 新增：註冊請求 Body
class UserCreate(BaseModel):
    email: EmailStr
    # 根據需求文件，密碼要求英數混合
    password: str = Field(..., min_length=8)
    role: UserRoleEnum # 讓 API 接受 Python Enum (e.g., "自由工作者")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        驗證密碼是否至少8碼且包含英文和數字
        """
        if not re.search(r'(?=.*[a-zA-Z])(?=.*[0-9])', v):
            raise ValueError('密碼必須包含英文和數字')
        if len(v) < 8:
            raise ValueError('密碼長度至少為 8 個字元')
        return v

# 2. 新增：註冊/查詢使用者的安全回應
class UserOut(BaseModel):
    user_id: str # 我們在 MySQL 中使用 CHAR(36)，但在 Pydantic 中視為 str
    email: EmailStr
    role: UserRoleEnum
    is_active: bool

    class Config:
        from_attributes = True # 舊版 Pydantic 叫 orm_mode = True