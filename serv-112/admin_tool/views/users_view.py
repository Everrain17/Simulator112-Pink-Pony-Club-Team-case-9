import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QAbstractItemView,
    QHeaderView)

from admin_tool.api_errors import humanize_api_error
from admin_tool.async_utils import AsyncTask, run_async
from admin_tool.views.user_dialog import UserDialog


logger = logging.getLogger("admin_tool.view.users")


class UsersView(QWidget):
    COLUMNS = ["ID", "Логин", "Роль", "Активен", "Создан"]
    PAGE_SIZE = 25

    def __init__(self, api, role: str = "admin", current_username: str = "", parent=None):
        super().__init__(parent)
        self.api = api
        self.role = role
        self.current_username = current_username
        self.page = 1
        self.pages = 1
        self.total = 0
        self._rows: list[dict] = []
        self._pending: AsyncTask | None = None

        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        title = QLabel("Пользователи")
        title.setObjectName("Title")
        v.addWidget(title)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Поиск по логину…")
        self.input_search.setClearButtonEnabled(True)
        self.input_search.returnPressed.connect(self._on_search)
        bar.addWidget(self.input_search, 3)

        self.combo_role = QComboBox()
        self.combo_role.addItem("Все роли", None)
        self.combo_role.addItem("Администраторы", "admin")
        self.combo_role.addItem("Преподаватели", "teacher")
        self.combo_role.addItem("Обучаемые", "trainee")
        self.combo_role.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.combo_role, 1)

        self.combo_active = QComboBox()
        self.combo_active.addItem("Все", None)
        self.combo_active.addItem("Активные", True)
        self.combo_active.addItem("Деактивированные", False)
        self.combo_active.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.combo_active, 1)

        btn_search = QPushButton("Найти")
        btn_search.clicked.connect(self._on_search)
        bar.addWidget(btn_search)

        v.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        v.addWidget(self.table, 1)

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

        self.btn_create = QPushButton("Добавить")
        self.btn_create.setObjectName("Primary")
        self.btn_create.clicked.connect(self._on_create)

        self.btn_edit = QPushButton("Редактировать")
        self.btn_edit.clicked.connect(self._on_edit)

        self.btn_reset = QPushButton("Сбросить пароль")
        self.btn_reset.clicked.connect(self._on_reset_password)

        self.btn_toggle = QPushButton("Деактивировать")
        self.btn_toggle.clicked.connect(self._on_toggle_active)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_refresh.clicked.connect(self.refresh)

        bottom.addWidget(self.btn_create)
        bottom.addWidget(self.btn_edit)
        bottom.addWidget(self.btn_reset)
        bottom.addWidget(self.btn_toggle)
        bottom.addWidget(self.btn_refresh)

        v.addLayout(bottom)

    # ------------------------------------------------------------- lifecycle

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
        return self.api.list_users(
            search=self.input_search.text().strip() or None,
            role=self.combo_role.currentData(),
            is_active=self.combo_active.currentData(),
            page=self.page,
            size=self.PAGE_SIZE,
        )

    def _on_data(self, data: dict):
        self._pending = None
        self._rows = data.get("items", [])
        self.total = int(data.get("total", 0))
        self.page = int(data.get("page", 1))
        self.pages = max(1, int(data.get("pages", 1)))

        self._fill_table()
        self._update_pagination()
        self._update_buttons()

    def _on_error(self, exc: Exception):
        self._pending = None
        logger.warning("list_users failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))

    def _on_op_error(self, exc: Exception):
        logger.error("users op failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))

    def _fill_table(self):
        self.table.setRowCount(len(self._rows))
        for r, u in enumerate(self._rows):
            self._set(r, 0, u["id"])
            self._set(r, 1, u["username"])
            self._set(r, 2, self._role_label(u["role"]))
            self._set(r, 3, "да" if u["is_active"] else "нет")
            created = (u.get("created_at") or "")[:19].replace("T", " ")
            self._set(r, 4, created)

    def _set(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value))
        if col in (0, 2, 3, 4):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    @staticmethod
    def _role_label(role: str) -> str:
        return {"admin": "Админ", "teacher": "Преподаватель", "trainee": "Обучаемый"}.get(role, role)

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

    # ------------------------------------------------------------- selection

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    def _update_buttons(self):
        u = self._selected()
        has = u is not None
        is_self = bool(u and u["username"] == self.current_username)

        self.btn_edit.setEnabled(has)
        self.btn_reset.setEnabled(has)
        self.btn_toggle.setEnabled(has and not is_self)

        if has:
            self.btn_toggle.setText(
                "Деактивировать" if u["is_active"] else "Активировать"
            )

    # ------------------------------------------------------------- actions

    def _on_create(self):
        logger.info("UI: create user dialog opened")
        dlg = UserDialog(
            self.api, user=None, parent=self,
            current_username=self.current_username,
        )
        if dlg.exec():
            logger.info("UI: user created")
            self.refresh()

    def _on_edit(self):
        u = self._selected()
        if not u:
            return
        logger.info("UI: edit user dialog opened for id=%s", u["id"])
        dlg = UserDialog(
            self.api, user=u, parent=self,
            current_username=self.current_username,
        )
        if dlg.exec():
            self.refresh()

    def _on_toggle_active(self):
        u = self._selected()
        if not u:
            return
        if u["username"] == self.current_username:
            QMessageBox.warning(
                self, "Нельзя", "Нельзя деактивировать собственную учётную запись."
            )
            return

        if u["is_active"]:
            answer = QMessageBox.question(
                self, "Деактивация",
                f"Деактивировать пользователя «{u['username']}»?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            logger.warning("UI: deactivating user id=%s username=%s",
                           u["id"], u["username"])
            uid = u["id"]
            run_async(
                lambda: self.api.deactivate_user(uid),
                on_done=lambda _: self.refresh(),
                on_error=self._on_op_error,
                parent=self,
            )
        else:
            logger.info("UI: reactivating user id=%s", u["id"])
            uid = u["id"]
            run_async(
                lambda: self.api.update_user(uid, {"is_active": True}),
                on_done=lambda _: self.refresh(),
                on_error=self._on_op_error,
                parent=self,
            )

    def _on_reset_password(self):
        u = self._selected()
        if not u:
            return
        answer = QMessageBox.question(
            self, "Сброс пароля",
            f"Сгенерировать новый пароль для «{u['username']}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        logger.warning("UI: password reset for user id=%s username=%s",
                       u["id"], u["username"])
        uid = u["id"]
        run_async(
            lambda: self.api.reset_user_password(uid),
            on_done=lambda resp: self._on_reset_done(u["username"], resp),
            on_error=self._on_op_error,
            parent=self,
        )

    def _on_reset_done(self, username: str, resp: dict):
        QMessageBox.information(
            self, "Новый пароль",
            f"Новый пароль для «{username}»:\n\n{resp['new_password']}\n\n"
            f"Передайте его пользователю лично.",
        )