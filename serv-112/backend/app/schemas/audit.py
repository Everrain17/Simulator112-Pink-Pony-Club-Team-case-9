from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    category: str
    action: str
    level: str
    user_id: int | None
    username: str | None
    entity_type: str | None
    entity_id: int | None
    details: dict
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    duration_ms: int | None


class AuditPage(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    size: int
    pages: int


class AuditCategory(BaseModel):
    code: str
    name: str
    critical: bool
    enabled: bool


class AuditCleanupRequest(BaseModel):
    older_than_days: int


class AuditCleanupResponse(BaseModel):
    deleted: int