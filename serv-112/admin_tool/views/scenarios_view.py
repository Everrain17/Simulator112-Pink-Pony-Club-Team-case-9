from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QCheckBox,
    QAbstractItemView, QHeaderView,
)


class ScenariosView(QWidget):
    """Просмотр сценариев (только чтение)."""

    COLUMNS = ["ID", "Название", "Сложность", "Активен", "Вид происшествия", "Описание"]
    PAGE_SIZE = 25

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.page = 1
        self.pages = 1
        self.total = 0
        self._rows: list[dict] = []
        self._incident_types: dict[str, str] = {}

        self._build()
        self._load_references()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        title = QLabel("Сценарии")
        title.setObjectName("Title")
        v.addWidget(title)

        hint = QLabel("Режим просмотра. Редактирование доступно преподавателю.")
        hint.setObjectName("Muted")
        v.addWidget(hint)

        # ---- toolbar ----
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Поиск по названию и описанию…")
        self.input_search.setClearButtonEnabled(True)
        self.input_search.returnPressed.connect(self._on_search)
        bar.addWidget(self.input_search, 3)

        self.combo_difficulty = QComboBox()
        self.combo_difficulty.addItem("Любая сложность", None)
        for i in range(1, 6):
            self.combo_difficulty.addItem(f"Сложность {i}", i)
        self.combo_difficulty.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.combo_difficulty, 1)

        self.chk_show_deleted = QCheckBox("Показать удалённые")
        self.chk_show_deleted.stateChanged.connect(self._on_search)
        bar.addWidget(self.chk_show_deleted)

        btn_search = QPushButton("Найти")
        btn_search.clicked.connect(self._on_search)
        bar.addWidget(btn_search)

        v.addLayout(bar)

        # ---- table ----
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        v.addWidget(self.table, 1)

        # ---- pagination ----
        bottom = QHBoxLayout()

        self.btn_prev = QPushButton("←")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self._on_prev)

        self.lbl_page = QLabel("1 / 1")
        self.lbl_page.setObjectName("Muted")

        self.btn_next = QPushButton("→")
        self.btn_next.setFixedWidth(40)
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

    # ------------------------------------------------------------ references

    def _load_references(self):
        try:
            types = self.api.list_incident_types()
            self._incident_types = {t["code"]: t["name"] for t in types}
        except Exception:
            self._incident_types = {}

    # ------------------------------------------------------------- lifecycle

    def refresh(self):
        try:
            data = self.api.list_scenarios(
                search=self.input_search.text().strip() or None,
                difficulty=self.combo_difficulty.currentData(),
                is_active=None if self.chk_show_deleted.isChecked() else True,
                page=self.page,
                size=self.PAGE_SIZE,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить сценарии: {exc}")
            return

        self._rows = data.get("items", [])
        self.total = int(data.get("total", 0))
        self.page = int(data.get("page", 1))
        self.pages = max(1, int(data.get("pages", 1)))

        self._fill_table()
        self._update_pagination()

    def _fill_table(self):
        self.table.setRowCount(len(self._rows))
        for r, s in enumerate(self._rows):
            self._set(r, 0, s["id"])
            self._set(r, 1, s["title"])
            self._set(r, 2, s["difficulty"])
            self._set(r, 3, "да" if s["is_active"] else "нет")

            code = s.get("incident_type_code")
            if code:
                label = f"{code} · {self._incident_types.get(code, '?')}"
            else:
                label = "—"
            self._set(r, 4, label)

            desc = s.get("description") or ""
            self._set(r, 5, desc if len(desc) < 140 else desc[:137] + "…")

    def _set(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value))
        if col in (0, 2, 3, 4):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------- toolbar

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

    def _update_pagination(self):
        self.lbl_page.setText(f"{self.page} / {self.pages}   (всего: {self.total})")
        self.btn_prev.setEnabled(self.page > 1)
        self.btn_next.setEnabled(self.page < self.pages)