from typing import Literal

from pydantic import BaseModel, Field

from app.core.audit_categories import ALL_CODES


AuditLevel = Literal["info", "warning", "error", "critical"]

AUDIT_RETENTION_MIN_DAYS = 180
AUDIT_RETENTION_MAX_DAYS = 3650


class AppSettingsRead(BaseModel):
    # аудит
    audit_categories: list[str] = Field(default_factory=lambda: list(ALL_CODES))
    audit_retention_days: int = AUDIT_RETENTION_MIN_DAYS
    audit_min_level: AuditLevel = "info"
    audit_sample_rate: float = 1.0

    # производительность
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30
    db_echo_sql: bool = False

    # резервное копирование
    backup_enabled: bool = False
    backup_hour: int = 3
    backup_retention_days: int = 30


class AppSettingsUpdate(BaseModel):
    audit_categories: list[str] | None = None
    audit_retention_days: int | None = Field(
        None,
        ge=AUDIT_RETENTION_MIN_DAYS,
        le=AUDIT_RETENTION_MAX_DAYS,
        description=(
            f"Срок хранения журналов, дней. "
            f"Минимум {AUDIT_RETENTION_MIN_DAYS} — требование ТЗ."
        ),
    )
    audit_min_level: AuditLevel | None = None
    audit_sample_rate: float | None = Field(None, ge=0.0, le=1.0)

    db_pool_size: int | None = Field(None, ge=1, le=100)
    db_max_overflow: int | None = Field(None, ge=0, le=200)
    db_pool_recycle: int | None = Field(None, ge=60, le=86400)
    db_pool_timeout: int | None = Field(None, ge=1, le=300)
    db_echo_sql: bool | None = None

    backup_enabled: bool | None = None
    backup_hour: int | None = Field(None, ge=0, le=23)
    backup_retention_days: int | None = Field(None, ge=1, le=3650)