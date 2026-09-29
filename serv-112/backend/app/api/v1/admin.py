import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import QueuePool
import httpx

from app import database
from app.api.deps import require_role
from app.config import settings
from app.core.audit_actions import AuditAction
from app.database import get_engine, get_session
from app.models.user import User
from app.redis_client import redis
from app.schemas.backup import (
    BackupCreateResponse,
    BackupRead,
    BackupReconcileResponse,
    RestoreResponse,
    SystemInfo,
)
from app.services.admin_guard import ensure_not_last_ok_backup
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.simcore_client import SimCoreClient

logger = logging.getLogger("app.admin")
router = APIRouter()




@router.get("/health")
async def health(_: User = Depends(require_role("admin"))):
    redis_ok = False
    db_ok = False

    try:
        redis_ok = bool(await redis.ping())
    except Exception:
        logger.exception("redis ping failed")

    try:
        async with database.AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        logger.exception("db ping failed")

    ok = redis_ok and db_ok
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"redis": redis_ok, "db": db_ok},
    )




@router.get("/system/info", response_model=SystemInfo)
async def system_info(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    engine = get_engine()
    pool = engine.pool

    if isinstance(pool, QueuePool):
        pool_size = pool.size()
        max_overflow = pool._max_overflow
        pool_recycle = pool._recycle
        pool_timeout = pool._timeout
    else:
        pool_size = int(getattr(pool, "size", lambda: 0)() or 0)
        max_overflow = int(getattr(pool, "_max_overflow", 0) or 0)
        pool_recycle = int(getattr(pool, "_recycle", -1) or -1)
        pool_timeout = int(getattr(pool, "_timeout", -1) or -1)

    url_safe = (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:***"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

    count, total = await BackupService(db).total_size()

    # --- ПРОВЕРКА КОМПОНЕНТОВ ЯДРА ---
    simcore_ok = False
    tts_ok = False
    qwen_ok = False

    async with httpx.AsyncClient(timeout=1.0, verify=False) as client:
        # 1. Проверяем C# SimCore
        try:
            state_data = await SimCoreClient().state()
            simcore_ok = "isRunning" in state_data
        except Exception:
            logger.debug("SimCore monitor ping failed")

        # 2. Проверяем TTS Server (FastAPI возвращает 404 на корень, что подтверждает его запуск)
        try:
            tts_res = await client.get("https://localhost:8000/")
            tts_ok = tts_res.status_code in (200, 404, 405)
        except Exception:
            logger.debug("TTS monitor ping failed")

        # 3. Проверяем Qwen (llama-server)
        try:
            qwen_res = await client.get("http://localhost:8080/health")
            qwen_ok = qwen_res.status_code == 200
        except Exception:
            try:
                qwen_res = await client.get("http://localhost:8080/")
                qwen_ok = qwen_res.status_code == 200
            except Exception:
                logger.debug("Qwen monitor ping failed")

    # СТРОГО ВОЗВРАЩАЕМ ВАЛИДНУЮ МОДЕЛЬ СХЕМЫ С УЧЕТОМ НОВЫХ ФЛАГОВ
    return SystemInfo(
        db_pool_size=pool_size,
        db_max_overflow=max_overflow,
        db_pool_recycle=pool_recycle,
        db_pool_timeout=pool_timeout,
        db_echo_sql=bool(engine.echo),
        db_url_safe=url_safe,
        backup_dir=settings.BACKUP_DIR,
        backup_count=count,
        backup_total_bytes=total,
        simcore_ok=simcore_ok,
        tts_ok=tts_ok,
        qwen_ok=qwen_ok,
    )


# ---------------------------------------------------------------- backups

@router.get("/backups", response_model=list[BackupRead])
async def list_backups(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    return await BackupService(db).list()


@router.post("/backups/reconcile", response_model=BackupReconcileResponse)
async def reconcile_backups(
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = BackupService(db)
    changes = await svc.reconcile()
    BackupService._last_reconcile_ts = __import__("time").monotonic()

    await AuditService(db).log(
        category="system",
        action=AuditAction.BACKUP_CREATED,
        user=current,
        level="info",
        details={"reconcile_changes": changes},
        force=True,
    )

    return BackupReconcileResponse(changes=changes)


@router.post(
    "/backups",
    response_model=BackupCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_backup(
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = BackupService(db)
    record = await svc.create_backup(user=current, kind="manual")

    action = (
        AuditAction.BACKUP_CREATED
        if record.status == "ok"
        else AuditAction.BACKUP_FAILED
    )
    await AuditService(db).log(
        category="system",
        action=action,
        user=current,
        entity_type="backup",
        entity_id=record.id,
        level="info" if record.status == "ok" else "error",
        details={
            "filename": record.filename,
            "size_bytes": record.size_bytes,
            "error": record.error,
        },
        force=True,
    )

    if record.status != "ok":
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"backup failed: {record.error}",
        )

    return BackupCreateResponse(backup=BackupRead.model_validate(record))


@router.post("/backups/{backup_id}/restore", response_model=RestoreResponse)
async def restore_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = BackupService(db)
    record = await svc.get(backup_id)
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")

    filename = record.filename
    current_id = current.id
    current_username = current.username

    db.info["skip_commit"] = True
    await db.commit()
    await db.close()

    try:
        await database.get_engine().dispose()
    except Exception:
        logger.exception("engine dispose before restore failed")

    ok, msg = await BackupService(db=None).restore(filename)

    try:
        await database.get_engine().dispose()
    except Exception:
        logger.exception("engine dispose after restore failed")

    try:
        await AuditService().log(
            category="system",
            action=(
                AuditAction.BACKUP_RESTORED if ok
                else AuditAction.BACKUP_FAILED
            ),
            user_id=current_id,
            username=current_username,
            entity_type="backup",
            entity_id=backup_id,
            level="warning" if ok else "error",
            details={"filename": filename, "message": msg},
            force=True,
        )
    except Exception:
        logger.exception("failed to write restore audit record")

    if not ok:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)
    return RestoreResponse(restored=True, message=msg)


@router.delete("/backups/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = BackupService(db)
    record = await svc.get(backup_id)
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")

    if record.status == "ok":
        await ensure_not_last_ok_backup(
            db, action="delete_backup", user=current,
        )

    filename = record.filename
    ok = await svc.delete(backup_id)
    if not ok:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "delete failed")

    await AuditService(db).log(
        category="system",
        action=AuditAction.BACKUP_DELETED,
        user=current,
        entity_type="backup",
        entity_id=backup_id,
        level="warning",
        details={"filename": filename},
        force=True,
    )
