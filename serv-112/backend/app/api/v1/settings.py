from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.audit_actions import AuditAction
from app.core.audit_categories import ALL_CODES
from app.database import get_session
from app.models.user import User
from app.schemas.settings import (
    AUDIT_RETENTION_MIN_DAYS,
    AppSettingsRead,
    AppSettingsUpdate,
)
from app.services.admin_guard import ensure_safe_audit_settings
from app.services.audit_service import AuditService
from app.services.settings_service import SettingsService


router = APIRouter()


def _to_read(data: dict) -> AppSettingsRead:
    return AppSettingsRead(
        audit_categories=data.get("audit_categories", list(ALL_CODES)),
        audit_retention_days=data.get(
            "audit_retention_days", AUDIT_RETENTION_MIN_DAYS
        ),
        audit_min_level=data.get("audit_min_level", "info"),
        audit_sample_rate=data.get("audit_sample_rate", 1.0),
        db_pool_size=data.get("db_pool_size", 5),
        db_max_overflow=data.get("db_max_overflow", 10),
        db_pool_recycle=data.get("db_pool_recycle", 1800),
        db_pool_timeout=data.get("db_pool_timeout", 30),
        db_echo_sql=data.get("db_echo_sql", False),
        backup_enabled=data.get("backup_enabled", False),
        backup_hour=data.get("backup_hour", 3),
        backup_retention_days=data.get("backup_retention_days", 30),
    )


@router.get("", response_model=AppSettingsRead)
async def get_settings(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    svc = SettingsService(db)
    return _to_read(await svc.get_all())


@router.put("", response_model=AppSettingsRead)
async def update_settings(
    payload: AppSettingsUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = SettingsService(db)
    before = await svc.get_all()

    data = payload.model_dump(exclude_unset=True, exclude_none=True)

    if "audit_categories" in data and data["audit_categories"] is not None:
        unknown = set(data["audit_categories"]) - set(ALL_CODES)
        if unknown:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"unknown categories: {sorted(unknown)}",
            )

    await ensure_safe_audit_settings(db, data, current)

    try:
        after = await svc.update_many(data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    changed: dict[str, dict] = {}
    for key in data.keys():
        old_value = before.get(key)
        new_value = after.get(key)
        if old_value != new_value:
            changed[key] = {"from": old_value, "to": new_value}

    await AuditService(db).log(
        category="settings",
        action=AuditAction.SETTINGS_UPDATED,
        user=current,
        details={"changed": changed},
        force=True,
    )

    return _to_read(after)