
import sys
import json
import webbrowser
from pathlib import Path

import httpx

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt


SERVER_HOST = "192.168.1.103"
SERVER_URL = f"https://{SERVER_HOST}:8010/api/v1"
FRONTEND_URL = f"https://{SERVER_HOST}:5000"


def detect_mode() -> str:
    exe_name = Path(
        sys.executable
        if getattr(sys, "frozen", False)
        else __file__
    ).stem.lower()

    if "student" in exe_name or "ученик" in exe_name:
        return "student"

    elif (
        "teacher" in exe_name
        or "преподаватель" in exe_name
        or "препод" in exe_name
    ):
        return "teacher"

    if len(sys.argv) > 1:
        return sys.argv[1].lower()

    return "student"


def login_and_check_role(
    username: str,
    password: str,
    expected_role: str,
):
    try:
        with httpx.Client(
            verify=False,
            timeout=10.0,
        ) as client:

            resp = client.post(
                f"{SERVER_URL}/auth/login",
                data={
                    "username": username,
                    "password": password,
                },
            )

            if resp.status_code == 401:
                return False, "Неверный логин или пароль"

            if resp.status_code != 200:
                return False, (
                    f"Ошибка сервера: {resp.status_code}"
                )

            token_data = resp.json()

            token = token_data.get(
                "access_token"
            )

            arm = token_data.get(
                "arm"
            )

            if not token:
                return False, "Сервер не вернул токен"

            me_resp = client.get(
                f"{SERVER_URL}/auth/me",
                headers={
                    "Authorization":
                        f"Bearer {token}"
                },
            )

            if me_resp.status_code != 200:
                return False, (
                    "Не удалось получить профиль"
                )

            me = me_resp.json()

            role = me.get("role")

            if role != expected_role:
                return False, (
                    "Такого пользователя не существует"
                )

            return True, {
                "token": token,
                "arm": arm,
                "me": me,
            }

    except Exception as e:
        return False, (
            f"Нет связи с сервером: {str(e)}"
        )


def run_launcher(mode: str):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    if mode == "student":
        expected_role = "trainee"
        target_page = "/index.html"
        title = (
            "Система-112 — Вход (Обучаемый)"
        )
    else:
        expected_role = "teacher"
        target_page = "/teacher.html"
        title = (
            "Система-112 — Вход (Преподаватель)"
        )

    dlg = QDialog()

    dlg.setWindowTitle(title)
    dlg.setFixedSize(320, 180)

    dlg.setStyleSheet(
        "background-color: #2b2b2b; "
        "color: white; "
        "font-size: 14px;"
    )

    layout = QVBoxLayout(dlg)

    lbl_title = QLabel(
        "Введите учетные данные"
    )

    lbl_title.setAlignment(
        Qt.AlignCenter
    )

    layout.addWidget(lbl_title)

    inp_user = QLineEdit()

    inp_user.setPlaceholderText(
        "Логин"
    )

    inp_user.setStyleSheet(
        "padding: 5px;"
    )

    layout.addWidget(inp_user)

    inp_pass = QLineEdit()

    inp_pass.setPlaceholderText(
        "Пароль"
    )

    inp_pass.setEchoMode(
        QLineEdit.Password
    )

    inp_pass.setStyleSheet(
        "padding: 5px;"
    )

    layout.addWidget(inp_pass)

    btn = QPushButton("Войти")

    btn.setStyleSheet(
        "background-color: #0078d4; "
        "color: white; "
        "padding: 5px; "
        "font-weight: bold;"
    )

    layout.addWidget(btn)

    status_lbl = QLabel("")

    status_lbl.setStyleSheet(
        "color: #ffffff;"
    )

    layout.addWidget(status_lbl)

    def on_login():
        status_lbl.setText(
            "Проверка..."
        )

        QApplication.processEvents()

        ok, result = login_and_check_role(
            inp_user.text().strip(),
            inp_pass.text(),
            expected_role,
        )

        if not ok:
            status_lbl.setText(result)
            return

        token = result["token"]
        arm = result["arm"]
        me = result["me"]

        student_id = me.get(
            "id",
            "",
        )

        student_name = me.get(
            "username",
            "",
        )

        url = (
            f"{FRONTEND_URL}{target_page}"
            f"?token={token}"
            f"&studentId={student_id}"
            f"&studentName={student_name}"
            f"&arm={arm or ''}"
        )

        webbrowser.open(url)

        dlg.accept()

    btn.clicked.connect(
        on_login
    )

    inp_pass.returnPressed.connect(
        on_login
    )

    dlg.exec()


if __name__ == "__main__":
    mode = detect_mode()
    run_launcher(mode)

