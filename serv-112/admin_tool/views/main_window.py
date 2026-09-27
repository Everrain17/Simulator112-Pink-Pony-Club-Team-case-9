import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QFrame, QStackedWidget, QLabel,
)

from admin_tool.views.audit_view import AuditView
from admin_tool.views.backups_view import BackupsView
from admin_tool.views.dashboard import DashboardView
from admin_tool.views.server_control import ServerControlView
from admin_tool.views.docker_view import DockerView
from admin_tool.views.settings_view import SettingsView
from admin_tool.views.users_view import UsersView


logger = logging.getLogger("admin_tool.main_window")


class MainWindow(QMainWindow):
    logout_requested = Signal()
    closed = Signal()

    def __init__(self, api, server, monitor, docker, username: str, role: str):
        super().__init__()
        self.api = api
        self.server = server
        self.monitor = monitor
        self.docker = docker
        self.username = username
        self.role = role

        self._factories: dict[int, callable] = {}
        self._loaded: dict[int, QWidget] = {}

        self.setWindowTitle(f"Система-112 · Администрирование — {username}")
        self.resize(1280, 800)
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------------- sidebar ----------------
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(16, 16, 16, 16)
        sb.setSpacing(8)

        title = QLabel("СИСТЕМА-112")
        title.setObjectName("Title")
        sb.addWidget(title)

        # ---------------- stack ----------------
        self.stack = QStackedWidget()

        tabs: list[tuple[str, callable]] = [
            ("Панель", lambda: DashboardView(self.api, self.server, self.monitor)),
            ("Сервер", lambda: ServerControlView(self.api, self.server, self.monitor)),
            ("Docker", lambda: DockerView(self.docker)),
            ("Пользователи", lambda: UsersView(
                self.api, role=self.role, current_username=self.username,
            )),
            ("Бэкапы", lambda: BackupsView(self.api)),
            ("Журнал", lambda: AuditView(self.api)),
            ("Настройки", lambda: SettingsView(self.api)),
        ]

        for index, (name, factory) in enumerate(tabs):
            self._factories[index] = factory
            self.stack.addWidget(QWidget())
            btn = QPushButton(name)
            btn.clicked.connect(self._make_switch(index))
            sb.addWidget(btn)

        sb.addStretch(1)

        # ---------------- footer ----------------
        user_lbl = QLabel(f"👤  {self.username}")
        user_lbl.setObjectName("Muted")
        sb.addWidget(user_lbl)

        btn_logout = QPushButton("Выйти")
        btn_logout.setObjectName("SecondaryButton")
        btn_logout.clicked.connect(self.logout_requested.emit)
        sb.addWidget(btn_logout)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self._ensure_loaded(0)
        self.stack.setCurrentIndex(0)

    def _make_switch(self, index: int):
        """Возвращает слот, который переключает стек и лениво создаёт виджет."""
        def _switch():
            self._ensure_loaded(index)
            self.stack.setCurrentIndex(index)
        return _switch

    def _ensure_loaded(self, index: int) -> None:
        if index in self._loaded:
            return
        factory = self._factories.get(index)
        if factory is None:
            return

        try:
            widget = factory()
        except Exception:
            logger.exception("failed to create view for tab %d", index)
            return

        old = self.stack.widget(index)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.stack.insertWidget(index, widget)
        self._loaded[index] = widget

    # ------------------------------------------------------------------ close

    def closeEvent(self, event):
        try:
            self.docker.stop_polling()
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(event)