import time
from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.audit_actions import AuditAction
from app.core.audit_categories import CATEGORIES
from app.database import get_session
from app.models.user import User
from app.schemas.audit import (
    AuditCategory,
    AuditCleanupRequest,
    AuditCleanupResponse,
    AuditPage,
    AuditLogRead,
)
from app.services.audit_service import AuditService
from app.services.settings_service import SettingsService

router = APIRouter()

_LEVEL_QUERY_PATTERN = r"^(info|warning|error|critical|info\+|warning\+|error\+|critical\+)$"

def _sanitize_for_list(x) -> AuditLogRead:
    """Персональные данные в массовом списке не отдаём."""
    item = AuditLogRead.model_validate(x)
    item.ip_address = None
    item.user_agent = None
    return item


@router.get("", response_model=AuditPage)
async def list_audit(
    category: str | None = Query(None),
    username: str | None = Query(None),
    action: str | None = Query(None),
    level: str | None = Query(None, pattern=_LEVEL_QUERY_PATTERN),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    svc = AuditService(db)
    try:
        items, total = await svc.list(
            category=category, username=username, action=action, level=level,
            since=since, until=until, page=page, size=size,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return AuditPage(
        items=[_sanitize_for_list(x) for x in items],
        total=total, page=page, size=size,
        pages=ceil(total / size) if size else 0,
    )


@router.get("/categories", response_model=list[AuditCategory])
async def list_categories(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    enabled = SettingsService.enabled_categories()
    return [
        AuditCategory(
            code=c["code"], name=c["name"], critical=c["critical"],
            enabled=c["code"] in enabled,
        )
        for c in CATEGORIES
    ]


@router.post("/cleanup", response_model=AuditCleanupResponse)
async def cleanup(
    payload: AuditCleanupRequest,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    t0 = time.monotonic()
    deleted = await AuditService(db).cleanup(payload.older_than_days)
    duration_ms = int((time.monotonic() - t0) * 1000)

    await AuditService(db).log(
        category="system",
        action=AuditAction.AUDIT_CLEANUP,
        user=current,
        level="warning",
        details={
            "older_than_days": payload.older_than_days,
            "deleted": deleted,
        },
        duration_ms=duration_ms,
        force=True,
    )
    return AuditCleanupResponse(deleted=deleted)