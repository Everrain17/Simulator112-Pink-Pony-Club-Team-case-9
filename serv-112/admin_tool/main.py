"""Точка входа Admin Tool."""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QDialog

from admin_tool import config as app_config
from admin_tool.api_client import ApiClient
from admin_tool.docker_manager import DockerManager
from admin_tool.logging_config import (
    install_excepthook, install_qt_message_handler, setup_logging,
)
from admin_tool.monitor import Monitor
from admin_tool.server_manager import ServerManager
from admin_tool.styles.theme import apply_theme
from admin_tool.views.login_dialog import LoginDialog
from admin_tool.views.main_window import MainWindow


PROJECT_ROOT = app_config.PROJECT_ROOT
BACKEND_DIR = app_config.BACKEND_DIR
LOG_DIR = PROJECT_ROOT / "logs"

logger = logging.getLogger("admin_tool.main")


class AppController(QObject):
    """Управляет жизненным циклом окон: login → main → logout → login → …"""

    def __init__(self, app, api, server, monitor, docker):
        super().__init__()
        self.app = app
        self.api = api
        self.server = server
        self.monitor = monitor
        self.docker = docker
        self._login: LoginDialog | None = None
        self._window: MainWindow | None = None
        self._intentional_logout = False

    def start(self) -> None:
        self._open_login()

    # ---------------------------------------------------------------- login

    def _open_login(self) -> None:
        self._intentional_logout = False
        self._login = LoginDialog(self.api, self.server, self.docker)
        self._login.finished.connect(self._on_login_finished)
        self._login.open()

    def _on_login_finished(self, result: int) -> None:
        dlg = self._login
        self._login = None
        if dlg is None:
            return
        dlg.deleteLater()

        if result != QDialog.DialogCode.Accepted:
            logger.info("login dialog cancelled — exiting")
            self.app.quit()
            return

        self._open_main(dlg.username or "", dlg.role or "")

    # ----------------------------------------------------------------- main

    def _open_main(self, username: str, role: str) -> None:
        self._window = MainWindow(
            api=self.api,
            server=self.server,
            monitor=self.monitor,
            docker=self.docker,
            username=username,
            role=role,
        )
        self._window.logout_requested.connect(self._on_logout_requested)
        self._window.closed.connect(self._on_window_closed)
        self.monitor.start()
        self._window.show()

    def _on_logout_requested(self) -> None:
        logger.info("logout requested")
        self._intentional_logout = True
        self.api.logout()
        if self._window is not None:
            self._window.close()

    def _on_window_closed(self) -> None:
        self.monitor.stop()
        window = self._window
        self._window = None
        if window is not None:
            window.deleteLater()

        if self._intentional_logout:
            self._open_login()
        else:
            logger.info("main window closed — exiting")
            self.app.quit()


def _try_autostart_backend(api: ApiClient, server: ServerManager, docker: DockerManager) -> None:
    """Проверяет, нужно ли поднять backend, и если да — поднимает."""
    if server.attach():
        logger.info("attached to already-running backend")
        return

    ping_ok = api.ping()
    port_busy = server.is_port_busy()

    if port_busy and not ping_ok:
        owner = server.find_port_owner()
        if owner and (owner["name"] or "").lower().startswith("python"):
            logger.warning(
                "port %s:%s busy by orphan python PID=%s — freeing",
                server.host, server.port, owner["pid"],
            )
            server.free_port()
            port_busy = server.is_port_busy()
            ping_ok = api.ping()

    if ping_ok:
        logger.info("backend already answers /healthz — not starting our own")
        return

    if port_busy:
        logger.warning(
            "port %s:%s busy but /healthz not responding — refusing to start",
            server.host, server.port,
        )
        return

    if not docker.is_docker_running():
        logger.warning("Docker Desktop not running — backend not started")
        return

    if not docker.is_compose_healthy():
        logger.warning(
            "Docker running but Postgres/Redis containers not healthy — "
            "backend not started",
        )
        return

    if not server.start():
        logger.error("failed to start backend automatically")


def main() -> int:
    root_logger = setup_logging(LOG_DIR)
    install_excepthook(root_logger)
    install_qt_message_handler(root_logger)

    logger.info("=" * 60)
    logger.info("Admin Tool starting (cwd=%s)", Path.cwd())
    logger.info(
        "TLS: enabled=%s ca=%s",
        app_config.SSL_ENABLED, app_config.SSL_CA_FILE,
    )

    try:
        app_config.ensure_certs()
    except Exception:
        logger.exception("не удалось подготовить TLS-сертификаты")
        return 2

    app = QApplication(sys.argv)
    apply_theme(app)

    api = ApiClient()
    server = ServerManager(
        BACKEND_DIR,
        host=app_config.SERVER_HOST,
        port=app_config.SERVER_PORT,
        tls_enabled=app_config.SSL_ENABLED,
        tls_cert_file=app_config.SSL_CERT_FILE,
        tls_key_file=app_config.SSL_KEY_FILE,
        tls_ca_file=(
            app_config.SSL_CA_FILE
            if app_config.SSL_ENABLED
            else None
        ),
        tls_verify_client=(
            app_config.SSL_VERIFY_CLIENT
            if app_config.SSL_ENABLED
            else False
        ),
    )
    monitor = Monitor(server, api)
    docker = DockerManager(PROJECT_ROOT)

    exit_reason = "clean"
    try:
        try:
            _try_autostart_backend(api, server, docker)
        except Exception:
            logger.exception("autostart backend failed — продолжаем в GUI")

        controller = AppController(app, api, server, monitor, docker)
        controller.start()
        return app.exec()
    except Exception:
        logger.exception("fatal error in main loop")
        exit_reason = "exception"
        raise
    finally:
        logger.info("Admin Tool exiting (reason=%s)", exit_reason)
        logging.shutdown()


if __name__ == "__main__":
    sys.exit(main())