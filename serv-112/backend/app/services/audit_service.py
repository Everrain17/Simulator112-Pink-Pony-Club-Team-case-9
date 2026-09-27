import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.core.audit_categories import CRITICAL_CODES
from app.core.request_context import (
    client_ip_ctx, request_id_ctx, user_agent_ctx,
)
from app.models.audit import AuditLog
from app.models.user import User
from app.services.settings_service import SettingsService


logger = logging.getLogger("app.audit")

_LEVEL_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}

_CLEANUP_BATCH = 5000


def _parse_level_filter(level: str) -> tuple[str, bool]:
    """Разбирает 'warning' / 'warning+' → (base, is_min)."""
    raw = (level or "").strip().lower()
    is_min = raw.endswith("+")
    base = raw[:-1] if is_min else raw
    if base not in _LEVEL_ORDER:
        raise ValueError(f"unknown level filter: {level!r}")
    return base, is_min


class AuditService:
    """Запись в audit_log.

    Ключевые принципы:
      - аудит НЕ участвует в бизнес-транзакции: пишется в отдельной
        сессии, поэтому не может ни закоммитить чужие изменения,
        ни откатиться вместе с бизнес-операцией;
      - аудит best-effort: ошибка логируется, но не пробрасывается;
      - cleanup выполняется батчами;
      - критические категории аудита пишутся ВСЕГДА, независимо от
        настроек — это требование ТЗ.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ---------------------------------------------------------- should_log?

    async def _should_log(self, category: str, level: str, force: bool) -> bool:
        if force:
            return True

        if category in CRITICAL_CODES:
            return True

        if not SettingsService.is_loaded():
            if self.db is None:
                logger.warning(
                    "audit settings not loaded and no session provided; "
                    "writing unconditionally (category=%s, level=%s)",
                    category, level,
                )
                return True
            await SettingsService(self.db).load_all()

        if category not in SettingsService.enabled_categories():
            return False

        min_level = SettingsService.get_cached("audit_min_level", "info")
        if not isinstance(min_level, str) or min_level not in _LEVEL_ORDER:
            logger.warning(
                "unknown audit_min_level=%r in settings; "
                "falling back to 'info'",
                min_level,
            )
            min_level = "info"

        if _LEVEL_ORDER.get(level, 0) < _LEVEL_ORDER[min_level]:
            return False

        if level == "info":
            try:
                rate = float(SettingsService.get_cached("audit_sample_rate", 1.0))
            except (TypeError, ValueError):
                rate = 1.0
            if rate < 1.0 and random.random() >= rate:
                return False
        return True

    # ----------------------------------------------------------------- write

    async def _write(self, entry: AuditLog) -> None:
        """Best-effort вставка в отдельной сессии."""
        try:
            async with database.AsyncSessionLocal() as session:
                session.add(entry)
                await session.commit()
        except Exception:
            logger.exception(
                "audit write failed: category=%s action=%s",
                entry.category, entry.action,
            )

    async def log(
        self,
        *,
        category: str,
        action: str,
        user: User | None = None,
        user_id: int | None = None,
        username: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        details: dict | None = None,
        level: str = "info",
        duration_ms: int | None = None,
        force: bool = False,
    ) -> None:
        try:
            if not await self._should_log(category, level, force):
                return
        except Exception:
            logger.exception("audit should_log failed: %s/%s", category, action)
            return

        if user is not None:
            user_id = user.id
            username = user.username

        entry = AuditLog(
            category=category,
            action=action,
            level=level,
            user_id=user_id,
            username=username,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            ip_address=client_ip_ctx.get(),
            user_agent=user_agent_ctx.get(),
            request_id=request_id_ctx.get(),
            duration_ms=duration_ms,
        )
        await self._write(entry)

    async def log_security(
        self,
        action: str,
        *,
        username: str | None = None,
        details: dict | None = None,
        level: str = "warning",
        force: bool = False,
    ) -> None:
        try:
            if not await self._should_log("security", level, force):
                return
        except Exception:
            logger.exception("audit should_log failed: security/%s", action)
            return

        entry = AuditLog(
            category="security",
            action=action,
            level=level,
            username=username,
            details=details or {},
            ip_address=client_ip_ctx.get(),
            user_agent=user_agent_ctx.get(),
            request_id=request_id_ctx.get(),
        )
        await self._write(entry)

    # ------------------------------------------------------------------ read

    async def list(
        self,
        *,
        category: str | None = None,
        username: str | None = None,
        action: str | None = None,
        level: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        conditions = []
        if category:
            conditions.append(AuditLog.category == category)
        if username:
            conditions.append(AuditLog.username.ilike(f"%{username.strip()}%"))
        if action:
            conditions.append(AuditLog.action == action)

        if level:
            base, is_min = _parse_level_filter(level)
            if is_min:
                allowed = [
                    name for name, order in _LEVEL_ORDER.items()
                    if order >= _LEVEL_ORDER[base]
                ]
                conditions.append(AuditLog.level.in_(allowed))
            else:
                conditions.append(AuditLog.level == base)

        if since:
            conditions.append(AuditLog.timestamp >= since)
        if until:
            conditions.append(AuditLog.timestamp <= until)

        base_q = select(AuditLog)
        if conditions:
            base_q = base_q.where(*conditions)

        total = (
            await self.db.execute(
                select(func.count()).select_from(base_q.subquery())
            )
        ).scalar_one()

        offset = (page - 1) * size
        items = (
            await self.db.execute(
                base_q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(size)
            )
        ).scalars().all()

        return list(items), total

    # --------------------------------------------------------------- cleanup

    async def cleanup(self, older_than_days: int) -> int:
        """Удаляет записи старше N дней порциями по _CLEANUP_BATCH."""
        if older_than_days <= 0:
            return 0

        threshold = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        total_deleted = 0

        while True:
            subq = (
                select(AuditLog.id)
                .where(AuditLog.timestamp < threshold)
                .limit(_CLEANUP_BATCH)
            )
            result = await self.db.execute(
                delete(AuditLog).where(AuditLog.id.in_(subq))
            )
            deleted = int(getattr(result, "rowcount", 0) or 0)
            total_deleted += deleted
            if deleted < _CLEANUP_BATCH:
                break

        return total_deleted