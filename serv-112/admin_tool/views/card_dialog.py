from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPlainTextEdit,
    QComboBox, QCheckBox, QPushButton, QMessageBox, QGroupBox, QGridLayout,
    QLabel,
)


CARD_FIELDS = [
    ("address",              "Адрес",               True),
    ("caller_name",          "ФИО заявителя",       False),
    ("incident_description", "Описание происшествия", True),
    ("entrance_number",      "Номер подъезда",      True),
]


class CardDialog(QDialog):
    """Создание или редактирование карточки происшествия."""

    def __init__(self, api, card: dict | None = None, parent=None):
        super().__init__(parent)
        self.api = api
        self.card = card
        self.result_data: dict | None = None

        is_edit = card is not None
        self.setWindowTitle("Карточка — редактирование" if is_edit else "Карточка — новая")
        self.setModal(True)
        self.setMinimumWidth(640)

        self._incident_types: list[dict] = []
        self._load_incident_types()

        self._build(is_edit)

    def _load_incident_types(self):
        try:
            self._incident_types = self.api.list_incident_types()
        except Exception:
            self._incident_types = []

    # ------------------------------------------------------------------ UI

    def _build(self, is_edit: bool):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        # ---- метаданные ----
        meta = QFormLayout()
        meta.setSpacing(10)

        self.combo_source = QComboBox()
        self.combo_source.addItem("Синтетическая", "synthetic")
        self.combo_source.addItem("Реальная", "real")
        self.combo_source.addItem("Импортированная", "import")
        meta.addRow("Источник", self.combo_source)

        self.combo_type = QComboBox()
        self.combo_type.addItem("— не задан —", None)
        for t in self._incident_types:
            self.combo_type.addItem(f"{t['code']} · {t['name']}", t["code"])
        meta.addRow("Вид происшествия", self.combo_type)

        self.input_subtype = QLineEdit()
        self.input_subtype.setPlaceholderText("например: Пожар в квартире")
        meta.addRow("Подтип", self.input_subtype)

        self.combo_priority = QComboBox()
        self.combo_priority.addItem("— не задан —", None)
        self.combo_priority.addItem("Низкий", "low")
        self.combo_priority.addItem("Средний", "medium")
        self.combo_priority.addItem("Высокий", "high")
        meta.addRow("Приоритет", self.combo_priority)

        v.addLayout(meta)

        # ---- raw_text ----
        v.addWidget(QLabel("Исходный текст карточки"))
        self.input_raw = QPlainTextEdit()
        self.input_raw.setPlaceholderText(
            "Например: «Горит квартира на пятом этаже, из окна идёт дым, люди внутри»"
        )
        self.input_raw.setFixedHeight(90)
        v.addWidget(self.input_raw)

        # ---- fields ----
        gb = QGroupBox("Поля карточки")
        grid = QGridLayout(gb)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self.field_widgets: dict[str, tuple[QLineEdit, QCheckBox]] = {}
        for row, (name, label, default_required) in enumerate(CARD_FIELDS):
            lbl = QLabel(label)
            edit = QLineEdit()
            edit.setPlaceholderText("значение")
            chk = QCheckBox("обязательное")
            chk.setChecked(default_required)

            grid.addWidget(lbl, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(chk, row, 2)

            self.field_widgets[name] = (edit, chk)
        v.addWidget(gb)

        # ---- кнопки ----
        row = QHBoxLayout()
        row.addStretch(1)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("Primary")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)

        row.addWidget(btn_cancel)
        row.addWidget(btn_save)
        v.addLayout(row)

        # ---- предзаполнение ----
        if is_edit:
            self._fill_from_card(self.card)

    def _fill_from_card(self, c: dict):
        idx = self.combo_source.findData(c.get("source", "synthetic"))
        if idx >= 0:
            self.combo_source.setCurrentIndex(idx)

        idx = self.combo_type.findData(c.get("incident_type_code"))
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)

        self.input_subtype.setText(c.get("subtype") or "")
        self.input_raw.setPlainText(c.get("raw_text") or "")

        idx = self.combo_priority.findData(c.get("priority"))
        if idx >= 0:
            self.combo_priority.setCurrentIndex(idx)

        fields = c.get("fields") or {}
        for name, (edit, chk) in self.field_widgets.items():
            spec = fields.get(name) or {}
            edit.setText(spec.get("value") or "")
            chk.setChecked(bool(spec.get("required", chk.isChecked())))

    # ---------------------------------------------------------------- save

    def _on_save(self):
        raw = self.input_raw.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "Проверка", "Исходный текст не может быть пустым")
            return

        fields_payload: dict[str, dict] = {}
        for name, (edit, chk) in self.field_widgets.items():
            value = edit.text().strip() or None
            fields_payload[name] = {
                "value": value,
                "required": chk.isChecked(),
            }

        payload = {
            "source": self.combo_source.currentData(),
            "raw_text": raw,
            "incident_type_code": self.combo_type.currentData(),
            "subtype": self.input_subtype.text().strip() or None,
            "priority": self.combo_priority.currentData(),
            "fields": fields_payload,
        }

        try:
            if self.card is None:
                self.result_data = self.api.create_card(payload)
            else:
                self.result_data = self.api.update_card(self.card["id"], payload)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", self._humanize(exc))
            return

        self.accept()

    @staticmethod
    def _humanize(exc: Exception) -> str:
        msg = str(exc)
        if "403" in msg:
            return "Недостаточно прав для этой операции"
        if "404" in msg:
            return "Карточка не найдена"
        if "422" in msg:
            return "Проверьте поля формы"
        return f"Ошибка: {msg}"