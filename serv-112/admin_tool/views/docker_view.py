import logging

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QFrame, QPushButton, QPlainTextEdit)
from PySide6.QtGui import QTextCursor


logger = logging.getLogger("admin_tool.view.docker")


class ServiceCard(QFrame):
    """Карточка сервиса: имя + состояние + порты."""

    def __init__(self, service: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.service = service

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)

        title_row = QHBoxLayout()
        self.name_lbl = QLabel(service)
        self.name_lbl.setStyleSheet("font-weight: 600;")
        self.badge = QLabel("—")
        self.badge.setObjectName("Badge")
        self.badge.setProperty("state", "wait")
        title_row.addWidget(self.name_lbl)
        title_row.addStretch(1)
        title_row.addWidget(self.badge)
        v.addLayout(title_row)

        self.status_lbl = QLabel("—")
        self.status_lbl.setObjectName("Muted")
        v.addWidget(self.status_lbl)

        self.ports_lbl = QLabel("")
        self.ports_lbl.setObjectName("Muted")
        v.addWidget(self.ports_lbl)

    def update_state(self, info: dict | None):
        if info is None:
            self._set_badge("—", "wait")
            self.status_lbl.setText("не создан")
            self.ports_lbl.setText("")
            return

        state = info.get("state", "")
        health = info.get("health", "")

        if state == "running" and health != "unhealthy":
            self._set_badge("running", "ok")
        elif state == "running":
            self._set_badge("unhealthy", "warn")
        elif state in ("exited", "dead"):
            self._set_badge("stopped", "error")
        elif state == "restarting":
            self._set_badge("restarting", "warn")
        else:
            self._set_badge(state or "unknown", "wait")

        self.status_lbl.setText(info.get("status", "—"))

        ports = info.get("ports") or []
        if ports and isinstance(ports[0], dict):
            pub = ", ".join(
                f"{p.get('PublishedPort')}→{p.get('TargetPort')}"
                for p in ports if p.get("PublishedPort")
            )
        else:
            pub = ", ".join(str(p) for p in ports) if ports else ""
        self.ports_lbl.setText(pub)

    def _set_badge(self, text: str, state: str):
        self.badge.setText(text)
        self.badge.setProperty("state", state)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)


class DockerView(QWidget):
    """Вкладка управления Docker Compose."""

    SERVICES = ["postgres", "redis"]

    def __init__(self, docker_manager, parent=None):
        super().__init__(parent)
        self.dm = docker_manager

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title = QLabel("Docker")
        title.setObjectName("Title")
        v.addWidget(title)

        self.docker_status = QLabel("Проверка Docker...")
        self.docker_status.setObjectName("Muted")
        v.addWidget(self.docker_status)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.cards: dict[str, ServiceCard] = {}
        for name in self.SERVICES:
            c = ServiceCard(name)
            self.cards[name] = c
            cards_row.addWidget(c, 1)
        v.addLayout(cards_row)

        row = QHBoxLayout()
        self.btn_up      = QPushButton("Запустить")
        self.btn_up.setObjectName("Primary")
        self.btn_down    = QPushButton("Остановить")
        self.btn_restart = QPushButton("Рестарт")
        self.btn_pull    = QPushButton("Обновить образы")
        for b in (self.btn_up, self.btn_down, self.btn_restart, self.btn_pull):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        self.btn_up.clicked.connect(lambda: (logger.info("UI: docker up"), self.dm.up())[-1])
        self.btn_down.clicked.connect(lambda: (logger.info("UI: docker down"), self.dm.down())[-1])
        self.btn_restart.clicked.connect(lambda: (logger.info("UI: docker restart"), self.dm.restart())[-1])
        self.btn_pull.clicked.connect(lambda: (logger.info("UI: docker pull"), self.dm.pull())[-1])

        self.dm.log_line.connect(self._append_log)
        self.dm.status_changed.connect(self._on_status)

        self.dm.start_polling()

    def _append_log(self, line: str):
        self.log.appendPlainText(line)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _on_status(self, status: dict):
        docker_running = status.get("docker_running", False)
        services = status.get("services") or {}

        if not docker_running:
            self.docker_status.setText("Docker Desktop не запущен")
            self.docker_status.setProperty("state", "error")
        else:
            self.docker_status.setText("Docker Desktop работает")
            self.docker_status.setProperty("state", "ok")
        self.docker_status.style().unpolish(self.docker_status)
        self.docker_status.style().polish(self.docker_status)

        for name, card in self.cards.items():
            card.update_state(services.get(name))

        for b in (self.btn_up, self.btn_down, self.btn_restart, self.btn_pull):
            b.setEnabled(docker_running)