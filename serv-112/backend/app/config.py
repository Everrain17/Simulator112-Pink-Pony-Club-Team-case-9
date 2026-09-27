import warnings
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CERT_DIR = PROJECT_ROOT / "certs"

_ENV_FILES = (
    str(PROJECT_ROOT / "backend" / ".env"),
    str(PROJECT_ROOT / ".env"),
)

_ALLOWED_TLS_VERSIONS = {"1.2", "1.3"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        extra="ignore",
    )

    APP_NAME: str = "system112-trainer"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8010

    # Python API -> C# SimCore
    SIMCORE_URL: str = "https://127.0.0.1:5000"
    SIMCORE_INTERNAL_TOKEN: str = "system112-dev-internal"
    SIMCORE_TIMEOUT_SEC: float = 45.0

    CORS_ORIGINS: str = (
        "http://127.0.0.1:5000,"
        "http://localhost:5000,"
        "https://127.0.0.1:5000,"
        "https://localhost:5000"
    )

    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "trainer"
    POSTGRES_PASSWORD: str = "trainer"
    POSTGRES_DB: str = "trainer"

    BACKUP_EXCLUDE_TABLES: list[str] = [
        "backup_records",
        "alembic_version",
    ]

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379

    JWT_SECRET: str = DEFAULT_JWT_SECRET
    JWT_ALG: str = "HS256"
    JWT_ACCESS_EXP_MIN: int = 15
    JWT_REFRESH_EXP_DAYS: int = 7

    PROJECT_ROOT: Path = PROJECT_ROOT
    BACKUP_DIR: str = str(PROJECT_ROOT / "backups")
    COMPOSE_FILE: str = "docker-compose.yml"
    POSTGRES_COMPOSE_SERVICE: str = "postgres"
    BACKUP_TIMEOUT_SEC: int = 600

    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_TIMEOUT: int = 30

    SSL_ENABLED: bool = True
    SSL_CERT_FILE: Path = CERT_DIR / "server.crt"
    SSL_KEY_FILE: Path = CERT_DIR / "server.key"
    SSL_CA_FILE: Path = CERT_DIR / "ca.crt"
    SSL_VERIFY_CLIENT: bool = False
    SSL_MIN_TLS_VERSION: str = "1.2"

    @staticmethod
    def _resolve_project_path(value: Path | str) -> Path:
        path = Path(value).expanduser()

        if path.is_absolute():
            return path

        return (PROJECT_ROOT / path).resolve()

    @model_validator(mode="after")
    def _normalize_paths(self) -> "Settings":
        self.SSL_CERT_FILE = self._resolve_project_path(
            self.SSL_CERT_FILE
        )
        self.SSL_KEY_FILE = self._resolve_project_path(
            self.SSL_KEY_FILE
        )
        self.SSL_CA_FILE = self._resolve_project_path(
            self.SSL_CA_FILE
        )
        return self

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        secret = self.JWT_SECRET

        if secret == DEFAULT_JWT_SECRET:
            if not self.DEBUG:
                raise ValueError(
                    "JWT_SECRET must be changed from default when DEBUG=false. "
                    "Run scripts/generate_env.py to generate a fresh secret."
                )

            warnings.warn(
                "[config] JWT_SECRET is set to the default value. "
                "Do not use this in production.",
                stacklevel=2,
            )

        elif len(secret) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters"
            )

        return self

    @model_validator(mode="after")
    def _check_tls(self) -> "Settings":
        if self.SSL_MIN_TLS_VERSION not in _ALLOWED_TLS_VERSIONS:
            raise ValueError(
                f"SSL_MIN_TLS_VERSION={self.SSL_MIN_TLS_VERSION!r} "
                f"не поддерживается; допустимо: "
                f"{sorted(_ALLOWED_TLS_VERSIONS)}"
            )

        if not self.SSL_ENABLED:
            if not self.DEBUG:
                raise ValueError(
                    "SSL_ENABLED=false запрещён при DEBUG=false: "
                    "требуется TLS внутри контура."
                )

            if self.SSL_VERIFY_CLIENT:
                raise ValueError(
                    "SSL_VERIFY_CLIENT=true требует SSL_ENABLED=true"
                )

            warnings.warn(
                "[config] TLS отключён. Это допустимо только в отладке.",
                stacklevel=2,
            )

            return self

        for path, label in (
            (self.SSL_CERT_FILE, "SSL_CERT_FILE"),
            (self.SSL_KEY_FILE, "SSL_KEY_FILE"),
        ):
            if not path.exists():
                raise ValueError(
                    f"{label} не найден: {path}. "
                    f"Сгенерируйте сертификаты: "
                    f"python scripts/generate_certs.py"
                )

        if self.SSL_VERIFY_CLIENT and not self.SSL_CA_FILE.exists():
            raise ValueError(
                f"SSL_VERIFY_CLIENT=true, но SSL_CA_FILE не найден: "
                f"{self.SSL_CA_FILE}. Выпустите CA и клиентские сертификаты: "
                f"python scripts/generate_client_cert.py"
            )

        return self

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )


settings = Settings()