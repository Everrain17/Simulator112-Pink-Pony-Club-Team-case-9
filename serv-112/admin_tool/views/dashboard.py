from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame)


class MetricCard(QFrame):
    """Карточка метрики: заголовок + значение."""

    def __init__(self, title: str, value: str = "—", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Panel")

        layout = QVBoxLayout(self)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("Muted")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("Title")

        layout.addWidget(title_lbl)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class DashboardView(QWidget):
    def __init__(self, api, server, monitor):
        super().__init__()
        self.api = api
        self.server = server
        self.monitor = monitor

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title = QLabel("Панель администратора")
        title.setObjectName("Title")
        v.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)

        self.card_state  = MetricCard("Статус сервера")
        self.card_pid    = MetricCard("PID")
        self.card_uptime = MetricCard("Uptime")
        self.card_cpu    = MetricCard("CPU, %")
        self.card_ram    = MetricCard("RAM, MB")
        self.card_redis  = MetricCard("Redis")
        self.card_api    = MetricCard("API")

        cards = [
            self.card_state, self.card_pid, self.card_uptime,
            self.card_cpu, self.card_ram, self.card_redis, self.card_api,
        ]
        for i, c in enumerate(cards):
            grid.addWidget(c, i // 4, i % 4)
        v.addLayout(grid)
        v.addStretch(1)

        self.monitor.metrics.connect(self._on_metrics)

    def _on_metrics(self, m: dict):
        self.card_state.set_value(m["state"])
        self.card_pid.set_value(str(m["pid"] or "—"))
        self.card_uptime.set_value(self._fmt_uptime(m["uptime"]))
        self.card_cpu.set_value(f'{m["cpu"]:.1f}')
        self.card_ram.set_value(f'{m["ram_mb"]:.1f}')
        self.card_redis.set_value("ok" if m["redis_ok"] else "—")
        self.card_api.set_value("ok" if m["api_ok"] else "—")

    @staticmethod
    def _fmt_uptime(sec: int) -> str:
        if not sec:
            return "—"
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"