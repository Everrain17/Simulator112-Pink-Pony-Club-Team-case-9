from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BackupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    kind: str
    status: str
    error: str | None
    created_at: datetime
    created_by_id: int | None


class BackupCreateResponse(BaseModel):
    backup: BackupRead
    requires_restart: bool = False


class BackupReconcileResponse(BaseModel):

    changes: int


class RestoreResponse(BaseModel):
    restored: bool
    message: str


class SystemInfo(BaseModel):

    db_pool_size: int
    db_max_overflow: int
    db_pool_recycle: int
    db_pool_timeout: int
    db_echo_sql: bool
    db_url_safe: str
    backup_dir: str
    backup_count: int
    backup_total_bytes: int
    
    # Новые поля мониторинга компонентов ядра
    simcore_ok: bool
    tts_ok: bool
    qwen_ok: bool
