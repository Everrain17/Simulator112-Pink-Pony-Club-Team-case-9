from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QPlainTextEdit, QCheckBox, QPushButton, QMessageBox,
)

class ScenarioDialog(QDialog):
    """Создание или редактирование сценария."""

    def __init__(self, api, scenario: dict | None = None, parent=None):
        super().__init__(parent)
        self.api = api
        self.scenario = scenario
        self.result_data: dict | None = None

        is_edit = scenario is not None
        self.setWindowTitle(
            "Редактирование сценария" if is_edit else "Новый сценарий"
        )
        self.setModal(True)
        self.setMinimumWidth(520)

        self._build(is_edit)

    def _build(self, is_edit: bool) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_title = QLineEdit()
        self.input_title.setMaxLength(255)
        self.input_title.setPlaceholderText("Например: Пожар в жилом доме")
        form.addRow("Название", self.input_title)

        self.input_difficulty = QSpinBox()
        self.input_difficulty.setRange(1, 5)
        self.input_difficulty.setValue(1)
        form.addRow("Сложность", self.input_difficulty)

        self.input_description = QPlainTextEdit()
        self.input_description.setPlaceholderText("Краткое описание ситуации")
        self.input_description.setFixedHeight(140)
        form.addRow("Описание", self.input_description)

        self.input_active = QCheckBox("Активен")
        self.input_active.setChecked(True)
        if not is_edit:
            self.input_active.setVisible(False)
        form.addRow("", self.input_active)

        v.addLayout(form)
        v.addStretch(1)

        # ---- buttons ----
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

        # ---- загрузка существующего ----
        if is_edit:
            self.input_title.setText(self.scenario.get("title", ""))
            self.input_difficulty.setValue(int(self.scenario.get("difficulty", 1)))
            self.input_description.setPlainText(self.scenario.get("description", ""))
            self.input_active.setChecked(bool(self.scenario.get("is_active", True)))

    def _on_save(self) -> None:
        title = self.input_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Проверка", "Название не может быть пустым")
            return

        payload = {
            "title": title,
            "difficulty": self.input_difficulty.value(),
            "description": self.input_description.toPlainText().strip(),
        }
        if self.scenario is not None:
            payload["is_active"] = self.input_active.isChecked()

        try:
            if self.scenario is None:
                self.result_data = self.api.create_scenario(payload)
            else:
                self.result_data = self.api.update_scenario(
                    self.scenario["id"], payload
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
            return "Сценарий не найден"
        if "422" in msg:
            return "Проверьте поля формы"
        return f"Ошибка: {msg}"