import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit, QLabel,
)
from PySide6.QtGui import QTextCursor


logger = logging.getLogger("admin_tool.view.server_control")


class ServerControlView(QWidget):
    """Вкладка управления backend-сервером: старт / стоп / рестарт + живой лог."""

    def __init__(self, api, server, monitor):
        super().__init__()
        self.api = api
        self.server = server
        self.monitor = monitor

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        v.addWidget(QLabel("Управление сервером"))

        row = QHBoxLayout()
        self.btn_start = QPushButton("Старт")
        self.btn_start.setObjectName("Primary")
        self.btn_stop = QPushButton("Стоп")
        self.btn_restart = QPushButton("Рестарт")
        self.btn_free_port = QPushButton("Освободить порт")
        self.btn_free_port.setObjectName("SecondaryButton")
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        row.addWidget(self.btn_restart)
        row.addWidget(self.btn_free_port)
        row.addStretch(1)
        v.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_restart.clicked.connect(self._on_restart)
        self.btn_free_port.clicked.connect(self._on_free_port)

        self.server.log_line.connect(self._append_log)
        self.server.state_changed.connect(self._on_state)

        self._on_state(self.server.state)

    # ---------------------------------------------------------------- actions

    def _on_start(self):
        logger.info("UI: server start clicked")
        self.server.start()

    def _on_stop(self):
        logger.info("UI: server stop clicked")
        self.server.stop()

    def _on_restart(self):
        logger.info("UI: server restart clicked")
        self.server.restart()

    def _on_free_port(self):
        logger.warning("UI: free port clicked")
        ok = self.server.free_port()
        if not ok:
            self._append_log("[gui] не удалось освободить порт — смотрите лог выше")

    # ---------------------------------------------------------------- state

    def _on_state(self, state: str):
        running = state in ("running", "starting")
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_restart.setEnabled(running)
        self.btn_free_port.setEnabled(not running)

    # ---------------------------------------------------------------- log

    def _append_log(self, line: str):
        self.log.appendPlainText(line)
        self.log.moveCursor(QTextCursor.MoveOperation.End)