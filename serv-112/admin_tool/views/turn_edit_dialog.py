from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QPlainTextEdit, QCheckBox, QDoubleSpinBox, QPushButton, QMessageBox,
)


class TurnEditDialog(QDialog):
    """Создание или редактирование одной реплики сценария."""

    def __init__(self, api, scenario_id: int, turn: dict | None = None, parent=None):
        super().__init__(parent)
        self.api = api
        self.scenario_id = scenario_id
        self.turn = turn
        self.result_data: dict | None = None

        is_edit = turn is not None
        self.setWindowTitle("Реплика — редактирование" if is_edit else "Реплика — новая")
        self.setModal(True)
        self.setMinimumWidth(560)

        self._ref_stages: list[dict] = []
        self._ref_emotions: list[dict] = []
        self._load_references()

        self._build()
        if is_edit:
            self._fill_from_turn(turn)

    # ------------------------------------------------------------ references

    def _load_references(self):
        try:
            self._ref_stages = self.api.list_dialog_stages()
        except Exception:
            self._ref_stages = []
        try:
            self._ref_emotions = self.api.list_emotional_states()
        except Exception:
            self._ref_emotions = []

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.combo_speaker = QComboBox()
        self.combo_speaker.addItem("Оператор", "operator")
        self.combo_speaker.addItem("Абонент", "caller")
        form.addRow("Говорящий", self.combo_speaker)

        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("Текст реплики")
        self.input_text.setFixedHeight(100)
        form.addRow("Текст", self.input_text)

        self.spin_timestamp = QDoubleSpinBox()
        self.spin_timestamp.setRange(0.0, 3600.0)
        self.spin_timestamp.setSingleStep(0.5)
        self.spin_timestamp.setSuffix(" сек")
        self.spin_timestamp.setValue(0.0)
        form.addRow("Метка времени", self.spin_timestamp)

        self.combo_stage = QComboBox()
        self.combo_stage.addItem("— не задан —", None)
        for s in self._ref_stages:
            self.combo_stage.addItem(f"{s['name']} ({s['code']})", s["code"])
        form.addRow("Этап диалога", self.combo_stage)

        self.combo_emotion = QComboBox()
        self.combo_emotion.addItem("— не задано —", None)
        for e in self._ref_emotions:
            self.combo_emotion.addItem(f"{e['name']} ({e['code']})", e["code"])
        form.addRow("Эмоция абонента", self.combo_emotion)

        self.input_expected = QLineEdit()
        self.input_expected.setPlaceholderText("например: fill_address")
        form.addRow("Ожидаемое действие", self.input_expected)

        checks = QHBoxLayout()
        self.chk_key = QCheckBox("Ключевой вопрос")
        self.chk_addr = QCheckBox("Содержит адрес")
        self.chk_name = QCheckBox("Содержит имя")
        checks.addWidget(self.chk_key)
        checks.addWidget(self.chk_addr)
        checks.addWidget(self.chk_name)
        checks.addStretch(1)
        form.addRow("", checks)

        v.addLayout(form)
        v.addStretch(1)

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

    def _fill_from_turn(self, t: dict):
        idx = self.combo_speaker.findData(t.get("speaker", "operator"))
        if idx >= 0:
            self.combo_speaker.setCurrentIndex(idx)

        self.input_text.setPlainText(t.get("text", ""))
        self.spin_timestamp.setValue(float(t.get("timestamp_sec") or 0.0))

        idx = self.combo_stage.findData(t.get("stage"))
        if idx >= 0:
            self.combo_stage.setCurrentIndex(idx)

        idx = self.combo_emotion.findData(t.get("emotional_marker"))
        if idx >= 0:
            self.combo_emotion.setCurrentIndex(idx)

        self.input_expected.setText(t.get("expected_action") or "")
        self.chk_key.setChecked(bool(t.get("is_key_question")))
        self.chk_addr.setChecked(bool(t.get("contains_address")))
        self.chk_name.setChecked(bool(t.get("contains_name")))

    # ---------------------------------------------------------------- save

    def _on_save(self):
        text = self.input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Проверка", "Текст реплики не может быть пустым")
            return

        payload = {
            "speaker": self.combo_speaker.currentData(),
            "text": text,
            "timestamp_sec": self.spin_timestamp.value(),
            "stage": self.combo_stage.currentData(),
            "expected_action": self.input_expected.text().strip() or None,
            "is_key_question": self.chk_key.isChecked(),
            "emotional_marker": self.combo_emotion.currentData(),
            "contains_address": self.chk_addr.isChecked(),
            "contains_name": self.chk_name.isChecked(),
        }

        try:
            if self.turn is None:
                self.result_data = self.api.create_turn(self.scenario_id, payload)
            else:
                self.result_data = self.api.update_turn(
                    self.scenario_id, self.turn["id"], payload
                )
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
            return "Реплика не найдена"
        if "422" in msg:
            return "Проверьте поля формы"
        return f"Ошибка: {msg}"