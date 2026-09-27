import logging
import re
from pathlib import Path

from admin_tool.styles.app_styles_vars import COLORS, FONTS, SIZES


logger = logging.getLogger("admin_tool.theme")

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _interpolate(text: str) -> str:
    """Подставляет значения токенов в {placeholder}-ы QSS."""
    vars_map: dict[str, str] = {
        **COLORS,
        "font_base": FONTS["base"],
        "font_size": str(FONTS["size"]),
        **{k: str(v) for k, v in SIZES.items()},
    }
    for key, value in vars_map.items():
        text = text.replace("{" + key + "}", value)

    leftovers = sorted(set(_PLACEHOLDER_RE.findall(text)))
    if leftovers:
        logger.warning(
            "QSS: неизвестные плейсхолдеры: %s", ", ".join(leftovers)
        )
    return text


def load_qss(name: str = "main.qss") -> str:
    """Читает QSS-файл из каталога styles/ и подставляет токены."""
    path = Path(__file__).with_name(name)
    return _interpolate(path.read_text(encoding="utf-8"))


def apply_theme(app) -> None:
    """Применяет глобальную тему ко всему приложению (main.qss)."""
    app.setStyleSheet(load_qss("main.qss"))


def apply_login_style(dialog) -> None:
    """Применяет стили логина к конкретному QDialog (login.qss)."""
    dialog.setStyleSheet(load_qss("login.qss"))