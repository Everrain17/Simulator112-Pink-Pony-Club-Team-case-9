from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QMessageBox, QLabel,
)

from admin_tool.api_errors import humanize_api_error
from admin_tool.async_utils import AsyncTask, run_async


class UserDialog(QDialog):
    """Создание или редактирование пользователя."""

    def __init__(
        self,
        api,
        user: dict | None = None,
        parent=None,
        current_username: str | None = None,
    ):
        super().__init__(parent)
        self.api = api
        self.user = user
        self.current_username = current_username or ""
        self._is_self = bool(user and user["username"] == self.current_username)
        self.result_data: dict | None = None
        self._task: AsyncTask | None = None

        is_edit = user is not None
        self.setWindowTitle(
            f"Редактирование: {user['username']}" if is_edit else "Новый пользователь"
        )
        self.setModal(True)
        self.setMinimumWidth(460)

        self._build(is_edit)
        if is_edit:
            self._fill_from_user(user)

    def _build(self, is_edit: bool):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("например: teacher_ivanov")
        self.input_username.setMaxLength(64)
        form.addRow("Логин", self.input_username)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        if is_edit:
            self.input_password.setPlaceholderText("оставьте пустым, чтобы не менять")
        else:
            self.input_password.setPlaceholderText("минимум 6 символов")
        form.addRow("Пароль", self.input_password)

        self.combo_role = QComboBox()
        self.combo_role.addItem("Преподаватель", "teacher")
        self.combo_role.addItem("Администратор", "admin")
        form.addRow("Роль", self.combo_role)

        self.chk_active = QCheckBox("Активен")
        self.chk_active.setChecked(True)
        if not is_edit:
            self.chk_active.setVisible(False)
        form.addRow("", self.chk_active)

        v.addLayout(form)

        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("Primary")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        row.addWidget(btn_cancel)
        row.addWidget(self.btn_save)
        v.addLayout(row)

    def _fill_from_user(self, u: dict):
        self.input_username.setText(u["username"])
        self.input_username.setReadOnly(True)

        if u["role"] == "trainee":
            self.combo_role.setVisible(False)
            self.hint.setText(
                "Обучаемых создаёт преподаватель. "
                "Администратор может только деактивировать их или сбросить пароль."
            )
        else:
            idx = self.combo_role.findData(u["role"])
            if idx >= 0:
                self.combo_role.setCurrentIndex(idx)

        self.chk_active.setChecked(bool(u["is_active"]))

        if self._is_self:
            self.combo_role.setEnabled(False)
            self.chk_active.setEnabled(False)
            self.hint.setText(
                "Редактирование своей учётной записи: можно сменить только пароль. "
                "Роль и признак активности защищены от случайного изменения."
            )

    def _on_save(self):
        if self._task is not None:
            return  # уже сохраняем

        password = self.input_password.text()
        is_edit = self.user is not None

        if not is_edit:
            username = self.input_username.text().strip()
            if len(username) < 3:
                QMessageBox.warning(self, "Проверка", "Логин — минимум 3 символа")
                return
            if len(password) < 6:
                QMessageBox.warning(self, "Проверка", "Пароль — минимум 6 символов")
                return

            payload = {
                "username": username,
                "password": password,
                "role": self.combo_role.currentData(),
            }
            self._start_save(lambda: self.api.create_user(payload))
            return

        # ---- edit ----
        payload: dict = {}
        if password:
            if len(password) < 6:
                QMessageBox.warning(self, "Проверка", "Пароль — минимум 6 символов")
                return
            payload["password"] = password

        if self.user["role"] != "trainee" and not self._is_self:
            new_role = self.combo_role.currentData()
            if new_role != self.user["role"]:
                payload["role"] = new_role

        if not self._is_self:
            if self.chk_active.isChecked() != self.user["is_active"]:
                payload["is_active"] = self.chk_active.isChecked()

        if not payload:
            self.accept()
            return

        uid = self.user["id"]
        self._start_save(lambda: self.api.update_user(uid, payload))

    def _start_save(self, fn):
        self.btn_save.setEnabled(False)
        self._task = run_async(
            fn,
            on_done=self._on_saved,
            on_error=self._on_save_error,
            parent=self,
        )

    def _on_saved(self, result):
        self._task = None
        self.result_data = result
        self.accept()

    def _on_save_error(self, exc: Exception):
        self._task = None
        self.btn_save.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))