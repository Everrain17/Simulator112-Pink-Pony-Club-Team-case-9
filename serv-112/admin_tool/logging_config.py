"""
Настройка логирования Admin Tool.

Пишет в logs/admin_tool.log с ротацией. Уровень:
    - INFO  в файл в обычном режиме;
    - DEBUG в файл при ADMIN_TOOL_DEBUG=1;
    - WARNING+ всегда дублируется в stderr.

Формат включает request_id: значение заполняется ApiClient'ом из заголовка
x-request-id ответа backend'а, чтобы связать запись клиента с audit_log.
"""

import logging
import logging.handlers
import os
import sys
import threading
from contextvars import ContextVar
from pathlib import Path


request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | req=%(request_id)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir: Path, debug: bool | None = None) -> logging.Logger:
    if debug is None:
        debug = os.getenv("ADMIN_TOOL_DEBUG", "").lower() in ("1", "true", "yes", "on")

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "admin_tool.log"

    root = logging.getLogger("admin_tool")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.propagate = False

    fmt = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    rid_filter = _RequestIdFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.addFilter(rid_filter)
    root.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    stderr_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    stderr_handler.addFilter(rid_filter)
    root.addHandler(stderr_handler)

    root.info(
        "Admin Tool logging initialized: file=%s level=%s",
        log_path, "DEBUG" if debug else "INFO",
    )
    return root


def install_excepthook(logger: logging.Logger) -> None:
    """Ловит необработанные исключения в главном потоке и в потоках.

    1) sys.excepthook — главный поток (Qt event loop).
    2) threading.excepthook — любой threading.
    """

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = _hook

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        thread_name = args.thread.name if args.thread else "?"
        logger.critical(
            "Unhandled exception in thread %s",
            thread_name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook


def install_qt_message_handler(logger: logging.Logger) -> None:
    """Перенаправляет qDebug/qWarning/qCritical в logging."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    level_map = {
        QtMsgType.QtDebugMsg:    logging.DEBUG,
        QtMsgType.QtInfoMsg:     logging.INFO,
        QtMsgType.QtWarningMsg:  logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg:    logging.CRITICAL,
    }
    qt_logger = logging.getLogger("admin_tool.qt")

    def _handler(mode, ctx, message: str) -> None:
        level = level_map.get(mode, logging.INFO)
        qt_logger.log(level, "%s", message)

    qInstallMessageHandler(_handler)