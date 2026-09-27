import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from admin_tool.api_errors import humanize_api_error


logger = logging.getLogger("admin_tool.view.backups")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class _OpSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _OpTask(QRunnable):
    """Блокирующий вызов API в QThreadPool."""

    def __init__(self, fn, signals: _OpSignals):
        super().__init__()
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:
            logger.exception("backup background op failed")
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                pass
            return
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            pass


class BackupsView(QWidget):
    COLUMNS = ["ID", "Файл", "Размер", "Тип", "Статус", "Создан", "Кем"]

    KIND_LABEL = {
        "manual": "ручной",
        "scheduled": "по расписанию",
        "recovered": "восстановлен",
    }
    STATUS_LABEL = {"ok": "ok", "failed": "ошибка"}

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self._rows: list[dict] = []
        self._pool = QThreadPool.globalInstance()
        self._op_inflight = False
        self._closed = False
        self._op_signals: _OpSignals | None = None
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        title = QLabel("Резервное копирование")
        title.setObjectName("Title")
        v.addWidget(title)

        hint = QLabel(
            "Восстановление заменяет текущее состояние базы данных. "
            "Убедитесь, что все занятия завершены. "
            "Операция может занять несколько минут."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        v.addWidget(hint)

        bar = QHBoxLayout()
        self.btn_create = QPushButton("Создать бэкап")
        self.btn_create.setObjectName("Primary")
        self.btn_create.clicked.connect(self._on_create)

        self.btn_restore = QPushButton("Восстановить")
        self.btn_restore.clicked.connect(self._on_restore)

        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_refresh.clicked.connect(self.refresh)

        self.btn_sync = QPushButton("Синхронизировать")
        self.btn_sync.setObjectName("SecondaryButton")
        self.btn_sync.setToolTip(
            "Сверить таблицу backup_records с файлами на диске "
            "и показать изменения."
        )
        self.btn_sync.clicked.connect(self._on_sync)

        bar.addWidget(self.btn_create)
        bar.addWidget(self.btn_restore)
        bar.addWidget(self.btn_delete)
        bar.addStretch(1)
        bar.addWidget(self.btn_sync)
        bar.addWidget(self.btn_refresh)
        v.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        h = self.table.horizontalHeader()
        for i in range(len(self.COLUMNS) - 1):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        v.addWidget(self.table, 1)

    # --------------------------------------------------------------- refresh

    def refresh(self):
        if self._closed:
            return
        try:
            self._rows = self.api.list_backups()
        except Exception as exc:
            if not self._closed:
                QMessageBox.critical(self, "Ошибка",
                                     humanize_api_error(exc))
            self._rows = []

        if self._closed:
            return

        self.table.setRowCount(len(self._rows))
        for r, b in enumerate(self._rows):
            self._set(r, 0, b["id"])
            self._set(r, 1, b["filename"])
            self._set(r, 2, _human_size(int(b.get("size_bytes") or 0)))
            self._set(r, 3, self.KIND_LABEL.get(b.get("kind", ""), b.get("kind", "")))
            self._set(r, 4, self.STATUS_LABEL.get(b.get("status", ""), b.get("status", "")))
            self._set(r, 5, (b.get("created_at") or "")[:19].replace("T", " "))
            self._set(r, 6, str(b.get("created_by_id") or "—"))
        self._update_buttons()

    def _set(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value))
        if col in (0, 2, 3, 4, 5, 6):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    def _update_buttons(self):
        b = self._selected()
        ok = b is not None and b.get("status") == "ok"
        busy = self._op_inflight
        self.btn_restore.setEnabled(ok and not busy)
        self.btn_delete.setEnabled(b is not None and not busy)

    def _set_busy(self, busy: bool):
        self._op_inflight = busy
        self.btn_create.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)
        self.btn_sync.setEnabled(not busy)
        if busy:
            self.btn_restore.setEnabled(False)
            self.btn_delete.setEnabled(False)
        else:
            self._update_buttons()

    # -------------------------------------------------------- background ops

    def _run_op(self, fn, on_done) -> None:
        if self._op_inflight or self._closed:
            return
        self._set_busy(True)

        signals = _OpSignals()
        self._op_signals = signals
        signals.finished.connect(on_done)
        signals.failed.connect(self._on_op_failed)
        self._pool.start(_OpTask(fn, signals))

    def _on_op_failed(self, msg: str):
        self._set_busy(False)
        if not self._closed:
            QMessageBox.critical(self, "Ошибка", msg)

    # --------------------------------------------------------------- actions

    def _on_create(self):
        logger.info("UI: create backup requested")
        self._run_op(self.api.create_backup, self._on_create_done)

    def _on_create_done(self, _result):
        self._set_busy(False)
        if self._closed:
            return
        QMessageBox.information(self, "Готово", "Резервная копия создана")
        self.refresh()

    def _on_sync(self):
        logger.info("UI: backups reconcile requested")
        self._run_op(self.api.reconcile_backups, self._on_sync_done)

    def _on_sync_done(self, result):
        self._set_busy(False)
        if self._closed:
            return
        changes = 0
        if isinstance(result, dict):
            try:
                changes = int(result.get("changes", 0))
            except (TypeError, ValueError):
                changes = 0
        if changes:
            QMessageBox.information(
                self, "Синхронизация",
                f"Изменений: {changes}.\nСписок обновлён.",
            )
        else:
            QMessageBox.information(self, "Синхронизация", "Список уже актуален.")
        self.refresh()

    def _on_restore(self):
        b = self._selected()
        if not b:
            return

        answer = QMessageBox.warning(
            self, "Восстановление",
            f"Восстановить базу из «{b['filename']}»?\n\n"
            f"Текущее состояние БД будет заменено.\n\n"
            f"Операция может занять до нескольких минут.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        logger.warning("UI: restore backup id=%s", b["id"])
        backup_id = b["id"]
        self._run_op(
            lambda: self.api.restore_backup(backup_id),
            self._on_restore_done,
        )

    def _on_restore_done(self, _result):
        self._set_busy(False)
        if self._closed:
            return
        QMessageBox.information(self, "Готово", "База восстановлена")
        self.refresh()

    def _on_delete(self):
        b = self._selected()
        if not b:
            return
        answer = QMessageBox.question(
            self, "Удаление",
            f"Удалить бэкап «{b['filename']}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        backup_id = b["id"]
        self._run_op(
            lambda: self.api.delete_backup(backup_id),
            self._on_delete_done,
        )

    def _on_delete_done(self, _result):
        self._set_busy(False)
        if self._closed:
            return
        self.refresh()

    # ---------------------------------------------------------------- close

    def closeEvent(self, event):
        self._closed = True
        if self._op_signals is not None:
            try:
                self._op_signals.finished.disconnect()
                self._op_signals.failed.disconnect()
            except Exception:
                pass
            self._op_signals = None
        super().closeEvent(event)