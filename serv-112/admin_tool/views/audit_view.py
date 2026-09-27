import logging
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QAbstractItemView,
    QHeaderView, QInputDialog,
)

from admin_tool.api_errors import humanize_api_error
from admin_tool.async_utils import AsyncTask, run_async


logger = logging.getLogger("admin_tool.view.audit")


def _fmt_local_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso[:19].replace("T", " ")


def _fmt_details(details: dict | None) -> str:
    if not details:
        return ""

    if "changed" in details and isinstance(details["changed"], dict):
        parts = []
        for key, change in details["changed"].items():
            if isinstance(change, dict) and "from" in change and "to" in change:
                old = change["from"]
                new = change["to"]
                parts.append(f"{key}: {old} → {new}")
            else:
                parts.append(f"{key}: {change}")
        text = "; ".join(parts) if parts else "(без изменений)"
    else:
        text = ", ".join(f"{k}={v}" for k, v in details.items())

    if len(text) > 160:
        text = text[:157] + "…"
    return text


_LEVEL_LABEL = {
    "info":     "INFO",
    "warning":  "WARN",
    "error":    "ERR",
    "critical": "CRIT",
}


class AuditView(QWidget):
    COLUMNS = ["Время", "Уровень", "Пользователь", "Категория", "Действие", "Сущность", "Детали"]
    PAGE_SIZE = 50

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.page = 1
        self.pages = 1
        self.total = 0
        self._rows: list[dict] = []
        self._pending: AsyncTask | None = None

        self._build()
        self._load_categories_async()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        title = QLabel("Журнал аудита")
        title.setObjectName("Title")
        v.addWidget(title)

        hint = QLabel("Время показано в локальной зоне. Данные хранятся в UTC.")
        hint.setObjectName("Muted")
        v.addWidget(hint)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Пользователь…")
        self.input_user.returnPressed.connect(self._on_search)
        bar.addWidget(self.input_user, 2)

        self.combo_category = QComboBox()
        self.combo_category.addItem("Все категории", None)
        self.combo_category.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.combo_category, 1)

        self.combo_level = QComboBox()
        self.combo_level.addItem("Любой уровень", None)
        self.combo_level.addItem("INFO и выше", "info+")
        self.combo_level.addItem("WARNING и выше", "warning+")
        self.combo_level.addItem("ERROR и выше", "error+")
        self.combo_level.addItem("Только CRITICAL", "critical")
        self.combo_level.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.combo_level, 1)

        btn_search = QPushButton("Найти")
        btn_search.clicked.connect(self._on_search)
        bar.addWidget(btn_search)

        self.btn_cleanup = QPushButton("Очистить старые…")
        self.btn_cleanup.setObjectName("SecondaryButton")
        self.btn_cleanup.clicked.connect(self._on_cleanup)
        bar.addWidget(self.btn_cleanup)

        v.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        h = self.table.horizontalHeader()
        for i in range(6):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        v.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.btn_prev = QPushButton("←"); self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self._on_prev)
        self.lbl_page = QLabel("1 / 1"); self.lbl_page.setObjectName("Muted")
        self.btn_next = QPushButton("→"); self.btn_next.setFixedWidth(40)
        self.btn_next.clicked.connect(self._on_next)
        bottom.addWidget(self.btn_prev)
        bottom.addWidget(self.lbl_page)
        bottom.addWidget(self.btn_next)
        bottom.addStretch(1)

        btn_refresh = QPushButton("Обновить")
        btn_refresh.setObjectName("SecondaryButton")
        btn_refresh.clicked.connect(self.refresh)
        bottom.addWidget(btn_refresh)
        v.addLayout(bottom)

    # --------------------------------------------------------------- async

    def _load_categories_async(self):
        run_async(
            self.api.list_audit_categories,
            on_done=self._on_categories,
            on_error=self._on_categories_error,
            parent=self,
        )

    def _on_categories(self, cats: list[dict]):
        for c in cats:
            self.combo_category.addItem(c["name"], c["code"])

    def _on_categories_error(self, exc: Exception):
        logger.warning("audit categories load failed: %s", exc)

    # -------------------------------------------------------------- lifecycle

    def refresh(self):
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None
        self._pending = run_async(
            self._fetch,
            on_done=self._on_data,
            on_error=self._on_error,
            parent=self,
        )

    def _fetch(self) -> dict:
        return self.api.list_audit(
            username=self.input_user.text().strip() or None,
            category=self.combo_category.currentData(),
            level=self.combo_level.currentData(),
            page=self.page,
            size=self.PAGE_SIZE,
        )

    def _on_data(self, data: dict):
        self._pending = None
        self._rows = data.get("items", [])
        self.total = int(data.get("total", 0))
        self.page = int(data.get("page", 1))
        self.pages = max(1, int(data.get("pages", 1)))

        self.table.setRowCount(len(self._rows))
        for r, x in enumerate(self._rows):
            self._set(r, 0, _fmt_local_time(x.get("timestamp")))
            level = (x.get("level") or "info").lower()
            self._set(r, 1, _LEVEL_LABEL.get(level, level.upper()))
            self._set(r, 2, x.get("username") or "—")
            self._set(r, 3, x.get("category") or "")
            self._set(r, 4, x.get("action") or "")

            ent = ""
            if x.get("entity_type"):
                ent = f"{x['entity_type']}#{x.get('entity_id') or '?'}"
            self._set(r, 5, ent or "—")

            self._set(r, 6, _fmt_details(x.get("details")))

        self.lbl_page.setText(f"{self.page} / {self.pages}   (всего: {self.total})")
        self.btn_prev.setEnabled(self.page > 1)
        self.btn_next.setEnabled(self.page < self.pages)

    def _on_error(self, exc: Exception):
        self._pending = None
        logger.warning("list_audit failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))

    def _set(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value))
        if col in (0, 1, 2, 3, 4, 5):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def _on_search(self):
        self.page = 1
        self.refresh()

    def _on_prev(self):
        if self.page > 1:
            self.page -= 1
            self.refresh()

    def _on_next(self):
        if self.page < self.pages:
            self.page += 1
            self.refresh()

    # --------------------------------------------------------------- cleanup

    def _on_cleanup(self):
        days, ok = QInputDialog.getInt(
            self, "Очистка журнала",
            "Удалить записи старше (дней):",
            value=365, minValue=1, maxValue=3650,
        )
        if not ok:
            return
        answer = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить все записи старше {days} дней?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            logger.info("audit cleanup cancelled by user")
            return
        logger.warning("UI: audit cleanup requested (older_than_days=%d)", days)
        self.btn_cleanup.setEnabled(False)
        run_async(
            lambda: self.api.cleanup_audit(days),
            on_done=self._on_cleanup_done,
            on_error=self._on_cleanup_error,
            parent=self,
        )

    def _on_cleanup_done(self, resp: dict):
        self.btn_cleanup.setEnabled(True)
        QMessageBox.information(self, "Готово", f"Удалено записей: {resp.get('deleted', 0)}")
        self.refresh()

    def _on_cleanup_error(self, exc: Exception):
        self.btn_cleanup.setEnabled(True)
        logger.error("audit cleanup failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))