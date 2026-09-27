import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine
from app import database
from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.audit_actions import AuditAction
from app.core.request_context import (
    client_ip_ctx, request_id_ctx, user_agent_ctx,
)
from app.core.settings_pubsub import subscriber_loop
from app.redis_client import close_redis, redis
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.settings_service import SettingsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")
scheduler_logger = logging.getLogger("app.backup.scheduler")


class _HealthCheckFilter(logging.Filter):
    HEALTH_PATHS = ("/healthz", "/api/v1/admin/health")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        try:
            path = args[2]
            status = args[4]
        except (IndexError, TypeError):
            return True
        return not (path in self.HEALTH_PATHS and status == 200)


logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())


def _current_pool_config(engine: AsyncEngine) -> dict:
    pool = engine.pool
    size_fn = getattr(pool, "size", None)
    pool_size = int(size_fn() if callable(size_fn) else 0) or 0
    return {
        "pool_size": pool_size,
        "max_overflow": int(getattr(pool, "_max_overflow", 0) or 0),
        "pool_recycle": int(getattr(pool, "_recycle", -1) or -1),
        "pool_timeout": int(getattr(pool, "_timeout", -1) or -1),
        "echo": bool(engine.echo),
    }


async def _backup_scheduler() -> None:
    while True:
        try:
            enabled = bool(SettingsService.get_cached("backup_enabled", False))
            if not enabled:
                await asyncio.sleep(3600)
                continue

            hour = int(SettingsService.get_cached("backup_hour", 3))
            now = datetime.now()
            next_run = now.replace(
                hour=hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)

            wait = (next_run - now).total_seconds()
            scheduler_logger.info(
                "backup scheduler: next run at %s (in %.0fs)",
                next_run,
                wait,
            )
            await asyncio.sleep(wait)

            record_id: int | None = None
            record_status = "failed"
            record_filename = ""
            record_error: str | None = None

            try:
                async with database.unit_of_work() as db:
                    svc = BackupService(db)
                    record = await svc.create_backup(
                        user=None,
                        kind="scheduled",
                    )
                    record_id = record.id
                    record_status = record.status
                    record_filename = record.filename
                    record_error = record.error

                    retention = int(
                        SettingsService.get_cached(
                            "backup_retention_days",
                            30,
                        )
                    )
                    await svc.cleanup_old(retention)

            except Exception:
                scheduler_logger.exception(
                    "scheduled backup transaction failed; "
                    "no DB changes were committed"
                )
                continue

            try:
                await AuditService().log(
                    category="system",
                    action=(
                        AuditAction.BACKUP_CREATED
                        if record_status == "ok"
                        else AuditAction.BACKUP_FAILED
                    ),
                    entity_type="backup",
                    entity_id=record_id,
                    level="info" if record_status == "ok" else "error",
                    details={
                        "filename": record_filename,
                        "kind": "scheduled",
                        "error": record_error,
                    },
                    force=True,
                )
            except Exception:
                scheduler_logger.exception(
                    "scheduled backup audit write failed"
                )

        except asyncio.CancelledError:
            scheduler_logger.info("backup scheduler cancelled")
            raise

        except Exception:
            scheduler_logger.exception("backup scheduler failed")
            await asyncio.sleep(600)


async def _reload_settings_from_db() -> None:
    async with database.AsyncSessionLocal() as db:
        await SettingsService(db).load_all()
    logger.info("settings cache reloaded from pub/sub signal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    BackupService.ensure_dir()

    async with database.AsyncSessionLocal() as db:
        await SettingsService(db).load_all()

    engine = database.get_engine()

    desired = {
        "pool_size": int(
            SettingsService.get_cached(
                "db_pool_size",
                settings.DB_POOL_SIZE,
            )
        ),
        "max_overflow": int(
            SettingsService.get_cached(
                "db_max_overflow",
                settings.DB_MAX_OVERFLOW,
            )
        ),
        "pool_recycle": int(
            SettingsService.get_cached(
                "db_pool_recycle",
                settings.DB_POOL_RECYCLE,
            )
        ),
        "pool_timeout": int(
            SettingsService.get_cached(
                "db_pool_timeout",
                settings.DB_POOL_TIMEOUT,
            )
        ),
        "echo": bool(
            SettingsService.get_cached(
                "db_echo_sql",
                False,
            )
        ),
    }

    current = _current_pool_config(engine)

    if any(current[k] != desired[k] for k in desired):
        logger.info(
            "reinit engine: %s → %s",
            current,
            desired,
        )
        await database.reinit_engine(**desired)

    async with database.AsyncSessionLocal() as db:
        await AuditService(db).log(
            category="system",
            action=AuditAction.APP_STARTED,
            level="info",
            details={
                "app": settings.APP_NAME,
                "debug": settings.DEBUG,
            },
            force=True,
        )

    scheduler_task = asyncio.create_task(_backup_scheduler())
    settings_sub_task = asyncio.create_task(
        subscriber_loop(_reload_settings_from_db)
    )

    try:
        yield

    finally:
        for task in (scheduler_task, settings_sub_task):
            task.cancel()

        for task in (scheduler_task, settings_sub_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            async with database.AsyncSessionLocal() as db:
                await AuditService(db).log(
                    category="system",
                    action=AuditAction.APP_STOPPED,
                    level="info",
                    force=True,
                )
        except Exception:
            logger.exception(
                "failed to write APP_STOPPED audit record"
            )

        await close_redis()
        await database.get_engine().dispose()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

# CORS для текущего HTTPS-фронтенда и локального HTTP-фронтенда.
# Не полагаемся на CORS_ORIGINS из .env: для локального запуска
# явно разрешаем именно те origin, с которых сейчас открывается UI.
CORS_ORIGINS = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_context_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_ctx.set(rid)
    client_ip_ctx.set(
        request.client.host if request.client else None
    )
    user_agent_ctx.set(
        request.headers.get("user-agent")
    )

    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logging.getLogger("uvicorn.error").exception(
        "Unhandled exception on %s",
        request.url.path,
    )

    try:
        async with database.AsyncSessionLocal() as db:
            await AuditService(db).log(
                category="errors",
                action=AuditAction.UNHANDLED_EXCEPTION,
                level="error",
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                force=True,
            )
    except Exception:
        logging.getLogger("uvicorn.error").exception(
            "Failed to persist unhandled exception to audit_log"
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


app.include_router(
    v1_router,
    prefix=settings.API_PREFIX,
)


@app.get("/healthz")
async def healthz():
    try:
        redis_ok = await redis.ping()
    except Exception:
        redis_ok = False

    return {
        "status": "ok",
        "redis": bool(redis_ok),
    }
