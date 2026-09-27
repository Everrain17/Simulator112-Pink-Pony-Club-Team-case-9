import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app import database
from app.config import settings
from app.models.backup import BackupRecord
from app.models.user import User


logger = logging.getLogger("app.backup")

_RECONCILE_LOCK_KEY = 0x1120_0001_0001
_RESTORE_LOCK_KEY = 0x1120_0001_0002

_RECONCILE_TTL_SEC = 30.0


class BackupService:
    """Работа с дампами: создание, список, restore, retention.

    Принципы:
      - дампы не читаются в память: pg_dump пишет прямо в файл,
        pg_restore читает прямо из файла;
      - reconcile / restore сериализуются advisory-локом;
      - параллельный restore невозможен даже между воркерами
        (session-level lock на отдельном соединении);
      - имя файла содержит uuid-суффикс — параллельные бэкапы в одну
        секунду не перетирают друг друга."""

    _last_reconcile_ts: float = 0.0
    RECONCILE_TTL_SEC: float = _RECONCILE_TTL_SEC

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ------------------------------------------------------------------ paths

    @property
    def backup_dir(self) -> Path:
        return Path(settings.BACKUP_DIR)

    @classmethod
    def ensure_dir(cls) -> None:
        Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)

    def _compose_argv(self, *args: str) -> list[str]:
        return [
            "docker", "compose",
            "-f", settings.COMPOSE_FILE,
            "exec", "-T", settings.POSTGRES_COMPOSE_SERVICE,
            *args,
        ]

    # ------------------------------------------------------------- meta sidecar

    def _meta_path(self, filename: str) -> Path:
        return self.backup_dir / (filename.rsplit(".", 1)[0] + ".meta.json")

    def _read_meta(self, filename: str) -> dict:
        p = self._meta_path(filename)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("cannot parse meta %s", p, exc_info=True)
            return {}

    def _write_meta(self, filename: str, meta: dict) -> None:
        p = self._meta_path(filename)
        try:
            p.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("cannot write meta %s", p, exc_info=True)

    # --------------------------------------------------------------- process

    async def _spawn_stream(
        self,
        cmd: list[str],
        *,
        stdout_to: Path | None = None,
        stdin_from: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[int, str]:
        cwd = str(settings.PROJECT_ROOT)
        effective_timeout = timeout or settings.BACKUP_TIMEOUT_SEC

        out_f = open(stdout_to, "wb") if stdout_to is not None else None
        in_f = open(stdin_from, "rb") if stdin_from is not None else None
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=cwd,
                    stdin=in_f if in_f is not None else asyncio.subprocess.DEVNULL,
                    stdout=out_f if out_f is not None else asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"docker not found: {exc}") from exc

            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                raise RuntimeError(
                    f"timeout after {effective_timeout}s: {' '.join(cmd)}"
                )

            err = stderr.decode("utf-8", "replace") if stderr else ""
            return proc.returncode or 0, err
        finally:
            if out_f is not None:
                out_f.close()
            if in_f is not None:
                in_f.close()

    # -------------------------------------------------------------- reconcile

    async def reconcile(self) -> int:
        """Синхронизирует backup_records с файлами на диске."""
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": _RECONCILE_LOCK_KEY},
        )

        files = {p.name for p in self.backup_dir.glob("*.dump")}
        rows = list((await self.db.execute(select(BackupRecord))).scalars().all())
        in_db = {r.filename for r in rows}

        changes = 0

        for r in rows:
            if r.status != "ok":
                continue
            if r.filename in files:
                continue
            logger.warning(
                "backup reconcile: drop DB record %s (file missing)",
                r.filename,
            )
            await self.db.delete(r)
            changes += 1

        for name in sorted(files - in_db):
            path = self.backup_dir / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            meta = self._read_meta(name)
            record = BackupRecord(
                filename=name,
                size_bytes=size,
                kind=meta.get("kind") or "recovered",
                status="ok",
                error=None,
                created_by_id=meta.get("created_by_id"),
            )
            self.db.add(record)
            changes += 1
            logger.info(
                "backup reconcile: add %s (kind=%s, size=%d)",
                name, record.kind, size,
            )

        if changes:
            await self.db.flush()
            logger.info("backup reconcile: %d changes", changes)
        return changes

    # ------------------------------------------------------------------- list

    async def list(
        self, *, limit: int = 200, force_reconcile: bool = False,
    ) -> list[BackupRecord]:
        """Список записей."""
        now = time.monotonic()
        stale = (
            now - BackupService._last_reconcile_ts
        ) >= self.RECONCILE_TTL_SEC
        if force_reconcile or stale:
            await self.reconcile()
            BackupService._last_reconcile_ts = time.monotonic()

        q = (
            select(BackupRecord)
            .order_by(BackupRecord.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def get(self, backup_id: int) -> BackupRecord | None:
        return await self.db.get(BackupRecord, backup_id)

    async def total_size(self) -> tuple[int, int]:
        count = 0
        total = 0
        for p in self.backup_dir.glob("*.dump"):
            try:
                total += p.stat().st_size
                count += 1
            except OSError:
                continue
        return count, total

    # ---------------------------------------------------------------- create

    async def create_backup(
        self, *, user: User | None = None, kind: str = "manual",
    ) -> BackupRecord:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{ts}_{uuid.uuid4().hex[:8]}.dump"
        path = self.backup_dir / filename

        cmd = self._compose_argv(
            "pg_dump",
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "-Fc",
        )

        logger.info("backup: running pg_dump → %s", path)
        try:
            returncode, stderr = await self._spawn_stream(cmd, stdout_to=path)
        except RuntimeError as exc:
            logger.error("backup spawn failed: %s", exc)
            path.unlink(missing_ok=True)
            return await self._persist_failed(filename, kind, user, str(exc))

        if returncode != 0:
            err = stderr.strip()[:1000] or "pg_dump failed"
            logger.error("backup failed: %s", err)
            path.unlink(missing_ok=True)
            return await self._persist_failed(filename, kind, user, err)

        size = path.stat().st_size
        self._write_meta(filename, {
            "kind": kind,
            "created_by_id": user.id if user else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": _RECONCILE_LOCK_KEY},
        )

        record = BackupRecord(
            filename=filename, size_bytes=size, kind=kind,
            status="ok", error=None,
            created_by_id=user.id if user else None,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        logger.info("backup ok: %s (%d bytes)", filename, size)
        return record

    async def _persist_failed(
        self, filename: str, kind: str, user: User | None, error: str,
    ) -> BackupRecord:
        record = BackupRecord(
            filename=filename, size_bytes=0, kind=kind,
            status="failed", error=error,
            created_by_id=user.id if user else None,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    # --------------------------------------------------------------- restore

    async def restore(self, filename: str) -> tuple[bool, str]:
        """pg_restore под session-level advisory-lock."""
        path = self.backup_dir / filename
        if not path.exists():
            return False, f"file missing: {filename}"

        conn = await self._try_acquire_restore_lock()
        if conn is None:
            return False, "restore already in progress"

        try:
            if not path.exists():
                return False, f"file missing: {filename}"

            cmd = self._compose_argv(
                "pg_restore",
                "-U", settings.POSTGRES_USER,
                "-d", settings.POSTGRES_DB,
                "--clean", "--if-exists", "--no-owner",
            )

            logger.warning("restore: pg_restore from %s", path)
            try:
                returncode, stderr = await self._spawn_stream(cmd, stdin_from=path)
            except RuntimeError as exc:
                logger.error("restore failed: %s", exc)
                return False, str(exc)

            if returncode != 0:
                err = stderr.strip()[:2000] or "pg_restore failed"
                logger.error("restore failed: %s", err)
                return False, err

            logger.warning("restore ok: %s", filename)
            return True, "ok"
        finally:
            try:
                await conn.close()
            except Exception:
                logger.warning("restore lock release failed", exc_info=True)

    async def _try_acquire_restore_lock(self) -> AsyncConnection | None:
        conn = await database.get_engine().connect()
        try:
            result = await conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": _RESTORE_LOCK_KEY},
            )
            got = bool(result.scalar())
            if not got:
                await conn.close()
                return None
            return conn
        except Exception:
            await conn.close()
            raise

    # ---------------------------------------------------------------- delete

    async def delete(self, backup_id: int) -> bool:
        record = await self.get(backup_id)
        if not record:
            return False

        path = self.backup_dir / record.filename
        meta = self._meta_path(record.filename)
        try:
            path.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
        except Exception:
            logger.exception("cannot unlink backup files for %s", record.filename)

        await self.db.delete(record)
        await self.db.flush()
        return True

    # --------------------------------------------------------------- retention

    async def cleanup_old(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        threshold = datetime.now(timezone.utc) - timedelta(days=retention_days)

        q = select(BackupRecord).where(BackupRecord.created_at < threshold)
        rows = list((await self.db.execute(q)).scalars().all())

        deleted = 0
        for row in rows:
            p = self.backup_dir / row.filename
            mp = self._meta_path(row.filename)
            try:
                p.unlink(missing_ok=True)
                mp.unlink(missing_ok=True)
            except Exception:
                logger.exception("cannot unlink files for %s", row.filename)
            await self.db.delete(row)
            deleted += 1

        if deleted:
            await self.db.flush()
            logger.info("backup retention: removed %d old records", deleted)
        return deleted