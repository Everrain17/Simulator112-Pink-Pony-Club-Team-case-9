from __future__ import annotations
import logging
import os
import subprocess
import sys
from pathlib import Path
logger = logging.getLogger("admin_tool.config")
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
BACKEND_DIR: Path = PROJECT_ROOT / "backend"
CERT_DIR: Path = PROJECT_ROOT / "certs"
ENV_FILE: Path = PROJECT_ROOT / ".env"
def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    result: dict[str, str] = {}
    try:
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ("'", '"')
            ):
                value = value[1:-1]
            result[key] = value
    except Exception:
        logger.exception("cannot read .env file %s", ENV_FILE)
    return result
_FILE_ENV: dict[str, str] = _read_env_file()
def _get(name: str, default: str | None = None) -> str | None:
    if name in os.environ:
        return os.environ[name]
    if name in _FILE_ENV:
        return _FILE_ENV[name]
    return default
def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("некорректное %s=%r — беру по умолчанию %r", name, raw, default)
        return default
def _get_path(name: str, default: Path) -> Path:
    raw = _get(name)
    if raw:
        return Path(raw).expanduser()
    return default
SERVER_HOST: str = _get("SERVER_HOST", "192.168.1.103") or "192.168.1.103"
SERVER_PORT: int = _get_int("SERVER_PORT", 8010)
API_PREFIX: str = _get("API_PREFIX", "/api/v1") or "/api/v1"
SSL_ENABLED: bool = _get_bool("SSL_ENABLED", True)
SSL_CERT_FILE: Path = _get_path("SSL_CERT_FILE", CERT_DIR / "server.crt")
SSL_KEY_FILE: Path = _get_path("SSL_KEY_FILE", CERT_DIR / "server.key")
SSL_CA_FILE: Path = _get_path("SSL_CA_FILE", CERT_DIR / "ca.crt")
SSL_VERIFY_CLIENT: bool = _get_bool("SSL_VERIFY_CLIENT", False)
SSL_CLIENT_CERT_FILE: Path = _get_path(
    "SSL_CLIENT_CERT_FILE", CERT_DIR / "client.crt"
)
SSL_CLIENT_KEY_FILE: Path = _get_path(
    "SSL_CLIENT_KEY_FILE", CERT_DIR / "client.key"
)
def scheme() -> str:
    return "https" if SSL_ENABLED else "http"
def server_url() -> str:
    return f"{scheme()}://{SERVER_HOST}:{SERVER_PORT}"
def httpx_verify() -> bool | str:
    """Что передать в httpx.Client(verify=...).
    Для HTTPS возвращаем путь к CA-файлу; для HTTP — True (не используется).
    """
    if not SSL_ENABLED:
        return True
    if not SSL_CA_FILE.exists():
        raise RuntimeError(
            f"SSL_CA_FILE не найден: {SSL_CA_FILE}. "
            f"Сгенерируйте сертификаты: python scripts/generate_certs.py"
        )
    return str(SSL_CA_FILE)
def httpx_cert() -> tuple[str, str] | None:
    if not SSL_ENABLED or not SSL_VERIFY_CLIENT:
        return None
    if not SSL_CLIENT_CERT_FILE.exists():
        raise RuntimeError(
            f"SSL_VERIFY_CLIENT=true, но клиентский сертификат не найден: "
            f"{SSL_CLIENT_CERT_FILE}. Запустите: "
            f"python backend/scripts/generate_client_cert.py --cn <имя>"
        )
    if not SSL_CLIENT_KEY_FILE.exists():
        raise RuntimeError(
            f"SSL_VERIFY_CLIENT=true, но клиентский ключ не найден: "
            f"{SSL_CLIENT_KEY_FILE}"
        )
    return (str(SSL_CLIENT_CERT_FILE), str(SSL_CLIENT_KEY_FILE))
def ensure_certs() -> None:
    """Сгенерировать серверные сертификаты, если их ещё нет.
    Клиентские сертификаты не генерируются автоматически: они
    персональные, у каждого рабочего места свои. Если SSL_VERIFY_CLIENT
    включён, но клиентских файлов нет — httpx_cert() бросит исключение
    при первом подключении, а main.py увидит ошибку и завершится.
    """
    if not SSL_ENABLED:
        return
    if (
        SSL_CERT_FILE.exists()
        and SSL_KEY_FILE.exists()
        and SSL_CA_FILE.exists()
    ):
        return
    script = PROJECT_ROOT / "backend" / "scripts" / "generate_certs.py"
    if not script.exists():
        raise RuntimeError(
            f"TLS-сертификаты отсутствуют, а скрипт генерации не найден: {script}"
        )
    logger.info("генерация TLS-сертификатов: %s", script)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Не удалось сгенерировать TLS-сертификаты.\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )
    logger.info("TLS-сертификаты созданы в %s", CERT_DIR)
