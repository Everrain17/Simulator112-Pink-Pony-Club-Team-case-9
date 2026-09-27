from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- auth ---

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    arm: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


# --- users ---

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)


class UserCreate(UserBase):
    """Создание пользователя."""
    password: str = Field(..., min_length=6, max_length=128)
    role: Literal["admin", "teacher", "trainee"] = "trainee"


class UserUpdate(BaseModel):
    """Частичное обновление."""
    password: str | None = Field(None, min_length=6, max_length=128)
    role: Literal["admin", "teacher"] | None = None
    is_active: bool | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    is_active: bool
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime

class MeResponse(UserRead):
    arm: str | None = None
    
class UserPage(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    size: int
    pages: int


class PasswordResetResponse(BaseModel):
    new_password: str