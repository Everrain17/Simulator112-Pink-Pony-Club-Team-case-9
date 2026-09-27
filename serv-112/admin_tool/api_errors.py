"""Типизированные ошибки API и их человекочитаемые формулировки."""

from __future__ import annotations

import httpx


class ApiError(Exception):
    """Ошибка обращения к API.

    kind — машиночитаемая категория для UI:
        auth | forbidden | not_found | validation | conflict
        | server | network | timeout | unknown
    status_code — HTTP-код, если ответ всё-таки был.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kind: str = "unknown",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.kind = kind

    def user_message(self) -> str:
        if self.kind == "auth":
            return "Неверный логин или пароль"
        if self.kind == "forbidden":
            return "Недостаточно прав для этой операции"
        if self.kind == "not_found":
            return "Запись не найдена"
        if self.kind == "validation":
            return f"Проверьте поля формы: {self.message}"
        if self.kind == "conflict":
            return self.message
        if self.kind == "server":
            return f"Ошибка сервера: {self.message}"
        if self.kind == "network":
            return "Сервер не отвечает. Проверьте подключение."
        if self.kind == "timeout":
            return "Превышено время ожидания ответа"
        return f"Ошибка: {self.message}"


_KIND_BY_STATUS = {
    400: "validation",
    401: "auth",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation",
}


def _status_kind(status: int) -> str:
    if status in _KIND_BY_STATUS:
        return _KIND_BY_STATUS[status]
    if 500 <= status < 600:
        return "server"
    return "unknown"


def _extract_message(response: httpx.Response) -> str:
    """Достаёт detail/message из FastAPI-ответа; иначе — сырой текст."""
    try:
        data = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:200] if text else f"HTTP {response.status_code}"

    if isinstance(data, dict):
        if "detail" in data:
            detail = data["detail"]
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                first = detail[0]
                if isinstance(first, dict):
                    loc = ".".join(str(x) for x in first.get("loc", ()))
                    msg = first.get("msg", "")
                    return f"{loc}: {msg}" if loc else str(msg)
                return str(first)
            return str(detail)
        if "message" in data:
            return str(data["message"])
    return f"HTTP {response.status_code}"


def raise_for_api(response: httpx.Response) -> None:
    """Бросает ApiError, если HTTP-статус >= 400."""
    if response.status_code < 400:
        return
    raise ApiError(
        _extract_message(response),
        status_code=response.status_code,
        kind=_status_kind(response.status_code),
    )


def humanize_api_error(exc: BaseException) -> str:
    """Готовая строка для QMessageBox по любому исключению."""
    if isinstance(exc, ApiError):
        return exc.user_message()
    return f"Ошибка: {exc}"