import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_categories import ALL_CODES
from app.core.settings_pubsub import publish_invalidate
from app.database import on_commit
from app.models.audit import AppSetting

logger = logging.getLogger("app.settings")

AUDIT_RETENTION_MIN_DAYS = 180

DEFAULT_SETTINGS: dict[str, Any] = {
    # аудит
    "audit_categories": ALL_CODES,
    "audit_retention_days": AUDIT_RETENTION_MIN_DAYS,
    "audit_min_level": "info",
    "audit_sample_rate": 1.0,
    # производительность
    "db_pool_size": 5,
    "db_max_overflow": 10,
    "db_pool_recycle": 1800,
    "db_pool_timeout": 30,
    "db_echo_sql": False,
    # бэкапы
    "backup_enabled": False,
    "backup_hour": 3,
    "backup_retention_days": 30,
}

KNOWN_KEYS: frozenset[str] = frozenset(DEFAULT_SETTINGS)

class SettingsService:
    """Настройки приложения в БД + кэш в памяти.

    Кэш делает чтение бесплатным: проверка «включена ли категория» идёт
    на каждом запросе, лишний SQL туда не нужен.

    Изменения распространяются между воркерами через Redis pub/sub
    (см. app.core.settings_pubsub). Redis здесь — только транспорт;
    источник истины всегда БД.

    Про commit: сервис НЕ коммитит сам — это делает unit_of_work.
    Локальный кэш и publish_invalidate выполняются через on_commit:
    если транзакция откатится, кэш не разойдётся с БД.
    """

    _cache: dict[str, Any] = {}
    _loaded: bool = False

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ read

    async def load_all(self) -> None:
        """Загрузить все настройки из БД в кеш. Вызывается из lifespan
        и из подписчика pub/sub."""
        rows = (await self.db.execute(select(AppSetting))).scalars().all()
        cache: dict[str, Any] = dict(DEFAULT_SETTINGS)
        for row in rows:
            value = row.value
            if isinstance(value, dict) and "value" in value:
                cache[row.key] = value["value"]
            else:
                cache[row.key] = value
        SettingsService._cache = cache
        SettingsService._loaded = True

    @classmethod
    def get_cached(cls, key: str, default: Any = None) -> Any:
        return cls._cache.get(key, DEFAULT_SETTINGS.get(key, default))

    async def get(self, key: str, default: Any = None) -> Any:
        if not SettingsService._loaded:
            await self.load_all()
        return SettingsService._cache.get(key, DEFAULT_SETTINGS.get(key, default))

    async def get_all(self) -> dict[str, Any]:
        if not SettingsService._loaded:
            await self.load_all()
        return dict(SettingsService._cache)

    # ----------------------------------------------------------------- write

    @staticmethod
    def _validate_keys(data: dict[str, Any]) -> None:
        unknown = set(data) - KNOWN_KEYS
        if unknown:
            raise ValueError(f"unknown settings keys: {sorted(unknown)}")

    async def _snapshot_from_db(self) -> dict[str, Any]:
        """Снимок настроек из БД в обход кэша.

        Нужен, потому что после update_many локальный кэш ещё НЕ
        обновлён (это произойдёт в on_commit). Роутер должен получить
        актуальный `after` для корректного diff'а в аудите.
        """
        rows = (await self.db.execute(select(AppSetting))).scalars().all()
        snapshot: dict[str, Any] = dict(DEFAULT_SETTINGS)
        for row in rows:
            value = row.value
            if isinstance(value, dict) and "value" in value:
                snapshot[row.key] = value["value"]
            else:
                snapshot[row.key] = value
        return snapshot

    def _schedule_cache_refresh(self, data: dict[str, Any]) -> None:
        """После commit обновить локальный кэш и разослать инвалидацию.

        Регистрируется через on_commit: сработает только если
        транзакция действительно закоммичена.
        """
        async def _apply() -> None:
            for k, v in data.items():
                SettingsService._cache[k] = v
            try:
                await publish_invalidate()
            except Exception:
                logger.exception("settings invalidate publish failed")

        on_commit(self.db, _apply)

    async def set_value(self, key: str, value: Any) -> None:
        """Сохранить одну настройку. Commit — на уровне UoW."""
        self._validate_keys({key: value})
        row = await self.db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value={"value": value})
            self.db.add(row)
        else:
            row.value = {"value": value}
        await self.db.flush()

        self._schedule_cache_refresh({key: value})

    async def update_many(self, data: dict[str, Any]) -> dict[str, Any]:
        """Массовое обновление настроек одной транзакцией."""
        if not data:
            return await self.get_all()
        self._validate_keys(data)

        for key, value in data.items():
            row = await self.db.get(AppSetting, key)
            if row is None:
                self.db.add(AppSetting(key=key, value={"value": value}))
            else:
                row.value = {"value": value}

        await self.db.flush()

        after = await self._snapshot_from_db()
        self._schedule_cache_refresh(data)
        return after

    # --------------------------------------------------------------- helpers

    @classmethod
    def enabled_categories(cls) -> set[str]:
        raw = cls._cache.get(
            "audit_categories", DEFAULT_SETTINGS["audit_categories"]
        )
        if isinstance(raw, list):
            return set(raw)
        return set(ALL_CODES)

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._loaded