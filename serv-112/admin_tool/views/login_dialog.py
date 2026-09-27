import logging

from PySide6.QtCore import Qt, QTimer, QRunnable, QThreadPool, QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton,
)

from admin_tool.api_errors import ApiError
from admin_tool.async_utils import AsyncTask, run_async
from admin_tool.styles.app_styles_vars import SIZES


logger = logging.getLogger("admin_tool.login")


class _PingSignals(QObject):
    result = Signal(bool)


class _PingTask(QRunnable):
    def __init__(self, api, signals: _PingSignals):
        super().__init__()
        self.api = api
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            ok = self.api.ping()
        except Exception:
            ok = False
        try:
            self.signals.result.emit(ok)
        except RuntimeError:
            pass


class _ActionSignals(QObject):
    finished = Signal(bool)


class _ActionTask(QRunnable):
    """Обёртка для тяжёлых блокирующих операций (compose up, server start)."""

    def __init__(self, fn, signals: _ActionSignals):
        super().__init__()
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            ok = bool(self.fn())
        except Exception:
            logger.exception("long-running action failed")
            ok = False
        try:
            self.signals.finished.emit(ok)
        except RuntimeError:
            pass


class LoginDialog(QDialog):
    POLL_INTERVAL_MS = 800
    MAX_TRIES = 20

    WAIT_DOCKER_TICKS = 90
    WAIT_COMPOSE_TICKS = 40
    WAIT_SERVER_TICKS = 25

    def __init__(self, api, server, docker, parent=None):
        super().__init__(parent)
        self.api = api
        self.server = server
        self.docker = docker
        self.username: str | None = None
        self.role: str | None = None

        self._tries = 0
        self._ping_inflight = False
        self._diag_inflight = False
        self._long_wait_left = 0
        self._busy = False

        self._poll: QTimer | None = None
        self._login_task: AsyncTask | None = None
        self._login_username: str = ""

        self.setObjectName("LoginDialog")
        self.setWindowTitle("Система-112 · Вход")
        self.setModal(True)
        self.setFixedSize(SIZES["login_width"], SIZES["login_height"])
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._pool = QThreadPool.globalInstance()

        self._ping_signals = _PingSignals()
        self._ping_signals.result.connect(self._on_ping_result)

        self._action_signals = _ActionSignals()
        self._action_signals.finished.connect(self._on_action_done)

        self._build()
        self._apply_style()
        self._start_server_poll()

    # ------------------------------------------------------------------ UI

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("LoginCard")
        outer.addWidget(card)

        v = QVBoxLayout(card)
        v.setContentsMargins(32, 32, 32, 32)
        v.setSpacing(12)

        title = QLabel("СИСТЕМА-112")
        title.setObjectName("LoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        subtitle = QLabel("Панель системного администратора")
        subtitle.setObjectName("LoginSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)

        v.addSpacing(12)

        self.input_user = QLineEdit()
        self.input_user.setObjectName("LoginInput")
        self.input_user.setPlaceholderText("Логин")
        v.addWidget(self.input_user)

        self.input_pass = QLineEdit()
        self.input_pass.setObjectName("LoginInput")
        self.input_pass.setPlaceholderText("Пароль")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.input_pass)

        self.status = QLabel("")
        self.status.setObjectName("LoginStatus")
        self.status.setProperty("state", "wait")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(48)
        v.addWidget(self.status)

        v.addStretch(1)

        row = QHBoxLayout()

        self.btn_retry = QPushButton("Запустить")
        self.btn_retry.setObjectName("SecondaryButton")
        self.btn_retry.setVisible(False)
        self.btn_retry.clicked.connect(self._on_retry)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_login = QPushButton("Войти")
        self.btn_login.setObjectName("LoginButton")
        self.btn_login.setDefault(True)
        self.btn_login.setEnabled(False)
        self.btn_login.clicked.connect(self._on_login)

        row.addWidget(self.btn_retry)
        row.addStretch(1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_login)
        v.addLayout(row)

        self.input_pass.returnPressed.connect(self._on_login)

    def _apply_style(self):
        from admin_tool.styles.theme import apply_login_style
        apply_login_style(self)

    def _set_status(self, text: str, state: str):
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # -------------------------------------------------------- server waiting

    def _start_server_poll(self):
        self._tries = 0
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.setInterval(self.POLL_INTERVAL_MS)
            self._poll.timeout.connect(self._schedule_ping)
        else:
            self._poll.stop()
        self._set_status("Подключение к серверу...", "wait")
        self._poll.start()
        self._schedule_ping()

    def _schedule_ping(self):
        if self._ping_inflight or self._busy:
            return
        self._ping_inflight = True
        self._pool.start(_PingTask(self.api, self._ping_signals))

    def _on_ping_result(self, ok: bool):
        self._ping_inflight = False

        if ok:
            if self._poll is not None:
                self._poll.stop()
            logger.info("backend reachable — login enabled")
            self._set_status("Сервер доступен", "ok")
            self.btn_login.setEnabled(True)
            self.btn_retry.setVisible(False)
            self.input_user.setFocus()
            return

        if self._long_wait_left > 0:
            self._long_wait_left -= 1
            secs = self._long_wait_left * self.POLL_INTERVAL_MS // 1000
            self._set_status(f"Ожидание... ~{secs} сек", "wait")
            return

        self._tries += 1
        if self._tries >= self.MAX_TRIES:
            if self._poll is not None:
                self._poll.stop()
            self._diagnose_failure()

    # ------------------------------------------------------------ diagnostics

    def _collect_diag(self) -> dict:
        """Собирает инфраструктурный статус."""
        return {
            "docker_running": self.docker.is_docker_running(),
            "compose_healthy": self.docker.is_compose_healthy(),
        }

    def _schedule_diag(self, on_done) -> None:
        if self._diag_inflight:
            return
        self._diag_inflight = True
        run_async(
            self._collect_diag,
            on_done=lambda diag: self._finish_diag(diag, on_done),
            on_error=self._on_diag_error,
            parent=self,
        )

    def _finish_diag(self, diag: dict, on_done) -> None:
        self._diag_inflight = False
        on_done(diag)

    def _on_diag_error(self, exc: Exception):
        self._diag_inflight = False
        logger.exception("diagnostics failed: %s", exc)
        self._set_status("Ошибка диагностики. Смотрите логи.", "error")
        self.btn_retry.setText("Повторить")
        self.btn_retry.setVisible(True)

    def _diagnose_failure(self):
        logger.warning("backend unreachable after %d tries — diagnosing", self._tries)
        self._set_status("Диагностика...", "wait")
        self._schedule_diag(self._on_diag_done)

    def _on_diag_done(self, diag: dict):
        if not diag["docker_running"]:
            logger.warning("diagnosis: Docker Desktop not running")
            self._set_status(
                "Docker Desktop не запущен.\n"
                "Запустите его — без него backend не работает.",
                "error",
            )
            self.btn_retry.setText("Запустить Docker Desktop")
            self.btn_retry.setVisible(True)
            return

        if not diag["compose_healthy"]:
            logger.warning("diagnosis: docker up but compose unhealthy")
            self._set_status(
                "Контейнеры Postgres и Redis не запущены.\n"
                "Docker работает, но база данных недоступна.",
                "error",
            )
            self.btn_retry.setText("Запустить контейнеры")
            self.btn_retry.setVisible(True)
            return

        logger.warning("diagnosis: infra ok, backend silent")
        self._set_status(
            "Backend не отвечает, хотя база данных доступна.\n"
            "Попробуйте запустить сервер.",
            "error",
        )
        self.btn_retry.setText("Запустить сервер")
        self.btn_retry.setVisible(True)

    # ----------------------------------------------------------------- retry

    def _on_retry(self):
        self.btn_retry.setVisible(False)
        self._tries = 0
        self._set_status("Проверка инфраструктуры...", "wait")
        self._schedule_diag(self._on_retry_diag)

    def _on_retry_diag(self, diag: dict):
        if not diag["docker_running"]:
            self._retry_start_docker()
            return
        if not diag["compose_healthy"]:
            self._retry_compose_up()
            return
        self._retry_start_server()

    def _retry_start_docker(self):
        started = self.docker.try_start_docker_desktop()
        if not started:
            logger.error("could not auto-start Docker Desktop")
            self._set_status(
                "Не удалось запустить Docker Desktop автоматически.\n"
                "Запустите вручную и нажмите «Повторить».",
                "error",
            )
            self.btn_retry.setText("Повторить")
            self.btn_retry.setVisible(True)
            return

        self._long_wait_left = self.WAIT_DOCKER_TICKS
        self._set_status("Ожидание запуска Docker Desktop...", "wait")
        self._start_server_poll()

    def _retry_compose_up(self):
        self._busy = True
        logger.info("attempting docker compose up")
        self._set_status("Запуск контейнеров Postgres и Redis...", "wait")
        self._pool.start(_ActionTask(
            self.docker.compose_up_blocking, self._action_signals
        ))

    def _retry_start_server(self):
        self._busy = True
        logger.info("attempting to start backend")
        self._set_status("Запуск backend...", "wait")
        self._pool.start(_ActionTask(self.server.start, self._action_signals))

    def _on_action_done(self, ok: bool):
        self._busy = False

        if not ok:
            logger.error("long-running action failed")
            self._set_status(
                "Не удалось выполнить действие. Проверьте логи.",
                "error",
            )
            self.btn_retry.setText("Повторить")
            self.btn_retry.setVisible(True)
            return

        self._set_status("Проверка состояния...", "wait")
        self._schedule_diag(self._on_action_diag)

    def _on_action_diag(self, diag: dict):
        if not diag["docker_running"]:
            self._long_wait_left = self.WAIT_DOCKER_TICKS
        elif not diag["compose_healthy"]:
            self._long_wait_left = self.WAIT_COMPOSE_TICKS
        else:
            self._long_wait_left = self.WAIT_SERVER_TICKS

        self._set_status("Ожидание запуска сервера...", "wait")
        self._start_server_poll()

    # ---------------------------------------------------------------- login

    def _on_login(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text()

        if not username or not password:
            self._set_status("Введите логин и пароль", "error")
            return

        if self._login_task is not None:
            return

        self.btn_login.setEnabled(False)
        self._set_status("Проверка...", "wait")
        self._login_username = username
        self._login_task = run_async(
            lambda: self._do_login(username, password),
            on_done=self._on_login_done,
            on_error=self._on_login_error,
            parent=self,
        )

    def _do_login(self, username: str, password: str) -> dict:
        """Логин и /me — в фоне. Если /me падает, гасим сессию."""
        self.api.login(username, password)
        try:
            return self.api.me()
        except Exception:
            self.api.logout()
            raise

    def _on_login_done(self, me: dict):
        self._login_task = None

        if me.get("role") != "admin":
            logger.warning("login denied: role=%s (admin required)", me.get("role"))
            self.api.logout()
            self._set_status("Доступ только для системного администратора", "error")
            self.btn_login.setEnabled(True)
            return

        self.username = self._login_username
        self.role = me["role"]
        logger.info("admin login accepted: user=%s", self.username)
        self._set_status("Добро пожаловать", "ok")
        self.accept()

    def _on_login_error(self, exc: Exception):
        self._login_task = None
        logger.warning("login rejected: %s", exc)
        self._set_status(self._humanize(exc), "error")
        self.btn_login.setEnabled(True)

    @staticmethod
    def _humanize(exc: Exception) -> str:
        if isinstance(exc, ApiError):
            if exc.kind == "auth":
                return "Неверный логин или пароль"
            if exc.kind == "network":
                return "Сервер не отвечает"
            if exc.kind == "timeout":
                return "Сервер не ответил вовремя"
            return exc.user_message()
        msg = str(exc)
        if "10061" in msg or "Connection refused" in msg:
            return "Сервер не отвечает"
        return f"Ошибка входа: {msg}"

    # ---------------------------------------------------------------- close

    def closeEvent(self, event):
        try:
            if self._poll is not None:
                self._poll.stop()
        except Exception:
            pass

        if self._login_task is not None:
            self._login_task.cancel()
            self._login_task = None

        try:
            self._ping_signals.result.disconnect(self._on_ping_result)
        except Exception:
            pass
        try:
            self._action_signals.finished.disconnect(self._on_action_done)
        except Exception:
            pass

        try:
            self._pool.waitForDone(2000)
        except Exception:
            pass

        super().closeEvent(event)