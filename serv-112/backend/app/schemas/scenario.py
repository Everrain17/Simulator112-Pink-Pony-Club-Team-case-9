from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ScenarioBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    difficulty: int = Field(1, ge=1, le=5)
    description: str = ""
    incident_type_code: str | None = Field(None, max_length=64)
    ekp_code: str | None = Field(None, max_length=64)
    caller_profile: dict | None = None


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    difficulty: int | None = Field(None, ge=1, le=5)
    description: str | None = None
    incident_type_code: str | None = Field(None, max_length=64)
    ekp_code: str | None = Field(None, max_length=64)
    caller_profile: dict | None = None
    is_active: bool | None = None


class ScenarioRead(ScenarioBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScenarioPage(BaseModel):
    items: list[ScenarioRead]
    total: int
    page: int
    size: int
    pages: int
