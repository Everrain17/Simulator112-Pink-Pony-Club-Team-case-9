from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QAbstractItemView, QHeaderView,
)

from admin_tool.views.turn_edit_dialog import TurnEditDialog


class TurnsDialog(QDialog):
    """Редактор реплик сценария."""

    def __init__(self, api, scenario: dict, parent=None):
        super().__init__(parent)
        self.api = api
        self.scenario = scenario
        self.scenario_id = scenario["id"]
        self._turns: list[dict] = []

        self.setWindowTitle(f"Реплики — {scenario['title']}")
        self.setModal(True)
        self.resize(900, 620)

        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        head = QLabel(f"Сценарий #{self.scenario_id}: {self.scenario['title']}")
        head.setObjectName("Title")
        v.addWidget(head)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["№", "Говорящий", "Текст", "Этап", "Эмоция", "Ключевой"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        v.addWidget(self.table, 1)

        row = QHBoxLayout()

        self.btn_up = QPushButton("▲")
        self.btn_up.setFixedWidth(36)
        self.btn_up.clicked.connect(self._on_move_up)

        self.btn_down = QPushButton("▼")
        self.btn_down.setFixedWidth(36)
        self.btn_down.clicked.connect(self._on_move_down)

        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addStretch(1)

        self.btn_add = QPushButton("Добавить")
        self.btn_add.setObjectName("Primary")
        self.btn_add.clicked.connect(self._on_add)

        self.btn_edit = QPushButton("Редактировать")
        self.btn_edit.clicked.connect(self._on_edit)

        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.clicked.connect(self._on_delete)

        btn_close = QPushButton("Закрыть")
        btn_close.setObjectName("SecondaryButton")
        btn_close.clicked.connect(self.accept)

        row.addWidget(self.btn_add)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_delete)
        row.addWidget(btn_close)

        v.addLayout(row)

    # ------------------------------------------------------------- lifecycle

    def refresh(self):
        try:
            self._turns = self.api.list_turns(self.scenario_id)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить реплики: {exc}")
            self._turns = []

        self._fill_table()
        self._update_buttons()

    def _fill_table(self):
        self.table.setRowCount(len(self._turns))
        for r, t in enumerate(self._turns):
            self._set(r, 0, t["turn_index"])
            self._set(r, 1, "Оператор" if t["speaker"] == "operator" else "Абонент")
            preview = t["text"]
            if len(preview) > 120:
                preview = preview[:117] + "…"
            self._set(r, 2, preview)
            self._set(r, 3, t.get("stage") or "—")
            self._set(r, 4, t.get("emotional_marker") or "—")
            self._set(r, 5, "да" if t.get("is_key_question") else "")

    def _set(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value))
        if col in (0, 1, 3, 4, 5):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------- selection

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._turns):
            return self._turns[idx]
        return None

    def _update_buttons(self):
        has = self._selected() is not None
        self.btn_edit.setEnabled(has)
        self.btn_delete.setEnabled(has)
        self.btn_up.setEnabled(has and self.table.currentRow() > 0)
        self.btn_down.setEnabled(has and self.table.currentRow() < len(self._turns) - 1)

    # ------------------------------------------------------------- actions

    def _on_add(self):
        dlg = TurnEditDialog(self.api, self.scenario_id, turn=None, parent=self)
        if dlg.exec():
            self.refresh()

    def _on_edit(self):
        t = self._selected()
        if not t:
            return
        dlg = TurnEditDialog(self.api, self.scenario_id, turn=t, parent=self)
        if dlg.exec():
            self.refresh()

    def _on_delete(self):
        t = self._selected()
        if not t:
            return
        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить реплику №{t['turn_index']}?\n\n{t['text'][:120]}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.delete_turn(self.scenario_id, t["id"])
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.refresh()

    def _on_move_up(self):
        self._move(-1)

    def _on_move_down(self):
        self._move(+1)

    def _move(self, delta: int):
        """Меняет порядок на delta позиций и отправляет reorder."""
        t = self._selected()
        if not t:
            return
        cur = self.table.currentRow()
        new = cur + delta
        if new < 0 or new >= len(self._turns):
            return

        # локально меняем порядок
        new_order = list(self._turns)
        new_order[cur], new_order[new] = new_order[new], new_order[cur]
        ordered_ids = [x["id"] for x in new_order]

        try:
            self.api.reorder_turns(self.scenario_id, ordered_ids)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return

        self.refresh()
        self.table.selectRow(new)