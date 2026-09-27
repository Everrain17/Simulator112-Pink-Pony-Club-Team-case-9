"""Ограничения администратора"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_actions import AuditAction
from app.core.audit_categories import CRITICAL_CODES
from app.models.backup import BackupRecord
from app.models.session import TrainingSession
from app.models.user import User
from app.services.audit_service import AuditService


logger = logging.getLogger("app.admin_guard")


async def _log_blocked(
    db: AsyncSession,
    *,
    user: User,
    reason: str,
    action: str,
    extra: dict | None = None,
) -> None:
    """Запись в audit_log о блокировке. force=True — эти события
    должны попадать в журнал даже если настройки аудита повреждены."""
    details = {"reason": reason, "action": action}
    if extra:
        details.update(extra)
    await AuditService(db).log(
        category="security",
        action=AuditAction.ADMIN_ACTION_BLOCKED,
        user=user,
        level="warning",
        force=True,
        details=details,
    )

async def ensure_no_active_session(
    db: AsyncSession,
    *,
    scenario_id: int | None,
    action: str,
    user: User,
) -> None:
    """Блокирует мутации учебных данных, пока идёт занятие."""
    conditions = [TrainingSession.finished_at.is_(None)]
    if scenario_id is not None:
        conditions.append(TrainingSession.scenario_id == scenario_id)

    active = int(
        (
            await db.execute(
                select(func.count())
                .select_from(TrainingSession)
                .where(*conditions)
            )
        ).scalar_one()
    )
    if not active:
        return

    await _log_blocked(
        db, user=user,
        reason="active_session",
        action=action,
        extra={"scenario_id": scenario_id, "active_count": active},
    )
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail=(
            "Нельзя изменять учебные данные во время активного занятия. "
            "Дождитесь завершения занятия или остановите его."
        ),
    )

async def ensure_not_last_ok_backup(
    db: AsyncSession,
    *,
    action: str,
    user: User,
) -> None:
    """Не даём удалить последний успешный бэкап."""
    ok_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(BackupRecord)
                .where(BackupRecord.status == "ok")
            )
        ).scalar_one()
    )
    if ok_count > 1:
        return

    await _log_blocked(
        db, user=user,
        reason="last_ok_backup",
        action=action,
        extra={"ok_count": ok_count},
    )
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail=(
            "Нельзя удалить последний успешный бэкап. "
            "Создайте новый бэкап перед удалением этого."
        ),
    )


async def ensure_not_last_active_admin(
    db: AsyncSession,
    *,
    exclude_user_id: int,
    action: str,
    user: User,
) -> None:
    """Не даём оставить систему без активного администратора."""
    remaining = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == "admin",
                    User.is_active.is_(True),
                    User.id != exclude_user_id,
                )
            )
        ).scalar_one()
    )
    if remaining > 0:
        return

    await _log_blocked(
        db, user=user,
        reason="last_active_admin",
        action=action,
        extra={"target_user_id": exclude_user_id},
    )
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail=(
            "Нельзя оставить систему без активного администратора. "
            "Сначала создайте или активируйте другого администратора."
        ),
    )

async def ensure_safe_audit_settings(
    db: AsyncSession,
    data: dict,
    user: User,
) -> None:
    """Запрещает ослабление настроек аудита."""
    if "audit_categories" in data:
        requested = set(data["audit_categories"] or [])
        removed_critical = sorted(CRITICAL_CODES - requested)
        if removed_critical:
            await _log_blocked(
                db, user=user,
                reason="critical_categories_removed",
                action="update_settings",
                extra={"removed": removed_critical},
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    "Нельзя отключать критические категории аудита: "
                    f"{removed_critical}"
                ),
            )

    if data.get("audit_min_level") not in (None, "info"):
        await _log_blocked(
            db, user=user,
            reason="audit_min_level_lowered",
            action="update_settings",
            extra={"requested": data.get("audit_min_level")},
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                "audit_min_level зафиксирован на 'info' — "
                "ТЗ требует аудит всех действий."
            ),
        )

    if data.get("audit_sample_rate") not in (None, 1.0):
        await _log_blocked(
            db, user=user,
            reason="audit_sample_rate_lowered",
            action="update_settings",
            extra={"requested": data.get("audit_sample_rate")},
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                "audit_sample_rate зафиксирован на 1.0 — "
                "ТЗ требует аудит всех действий."
            ),
        )