"""
Перечень категорий аудита.

Единый источник истины: используется и в backend (фильтр записи),
и в API (список категорий для GUI).
"""

from typing import Final


CATEGORIES: Final[list[dict]] = [
    {"code": "auth",      "name": "Аутентификация",        "critical": True},
    {"code": "users",     "name": "Пользователи",          "critical": True},
    {"code": "security",  "name": "Безопасность",          "critical": True},
    {"code": "scenarios", "name": "Сценарии и реплики",    "critical": False},
    {"code": "cards",     "name": "Карточки происшествий", "critical": False},
    {"code": "traces",    "name": "Траектории действий",   "critical": False},
    {"code": "sessions",  "name": "Сессии тренировок",     "critical": False},
    {"code": "system",    "name": "Системные операции",    "critical": False},
    {"code": "settings",  "name": "Настройки",             "critical": True},
    {"code": "errors",    "name": "Ошибки",                "critical": True},
]

ALL_CODES: Final[list[str]] = [c["code"] for c in CATEGORIES]
CRITICAL_CODES: Final[set[str]] = {c["code"] for c in CATEGORIES if c["critical"]}