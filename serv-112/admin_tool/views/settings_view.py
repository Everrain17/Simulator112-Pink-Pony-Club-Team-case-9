import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QCheckBox,
    QSpinBox, QPushButton, QMessageBox, QFormLayout
)

from admin_tool.api_errors import humanize_api_error
from admin_tool.async_utils import AsyncTask, run_async


logger = logging.getLogger("admin_tool.view.settings")

AUDIT_RETENTION_MIN_DAYS = 180


class SettingsView(QWidget):
    """Настройки системы: категории аудита, ретенция."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self._category_widgets: dict[str, tuple[QCheckBox, dict]] = {}
        self._pending: AsyncTask | None = None
        self._save_task: AsyncTask | None = None

        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("Title")
        v.addWidget(title)

        gb_audit = QGroupBox("Журнал аудита")
        gv = QVBoxLayout(gb_audit)
        gv.setSpacing(8)

        gb_perf = QGroupBox("Производительность (применится после рестарта backend)")
        pv = QFormLayout(gb_perf)

        self.spin_pool_size = QSpinBox()
        self.spin_pool_size.setRange(1, 100)
        pv.addRow("Размер пула соединений", self.spin_pool_size)

        self.spin_max_overflow = QSpinBox()
        self.spin_max_overflow.setRange(0, 200)
        pv.addRow("Max overflow", self.spin_max_overflow)

        self.spin_pool_recycle = QSpinBox()
        self.spin_pool_recycle.setRange(60, 86400)
        self.spin_pool_recycle.setSuffix(" сек")
        pv.addRow("Recycle соединений", self.spin_pool_recycle)

        self.spin_pool_timeout = QSpinBox()
        self.spin_pool_timeout.setRange(1, 300)
        self.spin_pool_timeout.setSuffix(" сек")
        pv.addRow("Timeout получения соединения", self.spin_pool_timeout)

        self.chk_echo_sql = QCheckBox("Логировать SQL (echo)")
        pv.addRow("", self.chk_echo_sql)

        v.addWidget(gb_perf)

        gb_backup = QGroupBox("Резервное копирование")
        bv = QFormLayout(gb_backup)

        self.chk_backup_enabled = QCheckBox("Включить ежедневный бэкап")
        bv.addRow("", self.chk_backup_enabled)

        self.spin_backup_hour = QSpinBox()
        self.spin_backup_hour.setRange(0, 23)
        self.spin_backup_hour.setSuffix(":00")
        bv.addRow("Час запуска", self.spin_backup_hour)

        self.spin_backup_retention = QSpinBox()
        self.spin_backup_retention.setRange(1, 3650)
        self.spin_backup_retention.setSuffix(" дней")
        bv.addRow("Хранить бэкапы", self.spin_backup_retention)

        v.addWidget(gb_backup)

        hint = QLabel(
            "Отметьте категории, которые нужно записывать в журнал. "
            "Критические категории отключать не рекомендуется."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        gv.addWidget(hint)

        self.cat_container = QWidget()
        self.cat_layout = QVBoxLayout(self.cat_container)
        self.cat_layout.setContentsMargins(0, 0, 0, 0)
        self.cat_layout.setSpacing(4)
        gv.addWidget(self.cat_container)

        retention_row = QHBoxLayout()
        retention_row.addWidget(QLabel("Хранить записи (дней):"))
        self.spin_retention = QSpinBox()

        self.spin_retention.setRange(AUDIT_RETENTION_MIN_DAYS, 3650)
        self.spin_retention.setValue(AUDIT_RETENTION_MIN_DAYS)
        self.spin_retention.setToolTip(
            f"Минимум {AUDIT_RETENTION_MIN_DAYS} дней — требование ТЗ "
            f"(хранение журналов безопасности не менее 6 месяцев)."
        )
        retention_row.addWidget(self.spin_retention)
        retention_row.addStretch(1)
        gv.addLayout(retention_row)

        v.addWidget(gb_audit)
        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)

        btn_reload = QPushButton("Сбросить")
        btn_reload.setObjectName("SecondaryButton")
        btn_reload.clicked.connect(self.refresh)

        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("Primary")
        self.btn_save.clicked.connect(self._on_save)

        row.addWidget(btn_reload)
        row.addWidget(self.btn_save)
        v.addLayout(row)

    def _rebuild_categories(self, categories: list[dict], enabled: set[str]):
        while self.cat_layout.count():
            item = self.cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._category_widgets.clear()

        for cat in categories:
            cb = QCheckBox(cat["name"] + (" *" if cat["critical"] else ""))
            cb.setChecked(cat["code"] in enabled)
            if cat["critical"]:
                cb.setToolTip("Критическая категория — отключение снизит уровень аудита")
            self.cat_layout.addWidget(cb)
            self._category_widgets[cat["code"]] = (cb, cat)

    # ------------------------------------------------------------- lifecycle

    def refresh(self):
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None
        self._pending = run_async(
            self._fetch_all,
            on_done=self._on_data,
            on_error=self._on_error,
            parent=self,
        )

    def _fetch_all(self) -> dict:
        return {
            "cats": self.api.list_audit_categories(),
            "settings": self.api.get_settings(),
        }

    def _on_data(self, payload: dict):
        self._pending = None
        cats = payload["cats"]
        settings = payload["settings"]

        enabled = {c["code"] for c in cats if c["enabled"]}
        self._rebuild_categories(cats, enabled)

        retention = int(
            settings.get("audit_retention_days", AUDIT_RETENTION_MIN_DAYS)
        )
        if retention < AUDIT_RETENTION_MIN_DAYS:
            retention = AUDIT_RETENTION_MIN_DAYS
        self.spin_retention.setValue(retention)

        self.spin_pool_size.setValue(int(settings.get("db_pool_size", 5)))
        self.spin_max_overflow.setValue(int(settings.get("db_max_overflow", 10)))
        self.spin_pool_recycle.setValue(int(settings.get("db_pool_recycle", 1800)))
        self.spin_pool_timeout.setValue(int(settings.get("db_pool_timeout", 30)))
        self.chk_echo_sql.setChecked(bool(settings.get("db_echo_sql", False)))

        self.chk_backup_enabled.setChecked(bool(settings.get("backup_enabled", False)))
        self.spin_backup_hour.setValue(int(settings.get("backup_hour", 3)))
        self.spin_backup_retention.setValue(int(settings.get("backup_retention_days", 30)))

    def _on_error(self, exc: Exception):
        self._pending = None
        logger.warning("settings load failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))

    def _on_save(self):
        if self._save_task is not None:
            return

        selected = [code for code, (cb, _) in self._category_widgets.items() if cb.isChecked()]

        critical_off = [
            code for code, (cb, cat) in self._category_widgets.items()
            if cat["critical"] and not cb.isChecked()
        ]
        if critical_off:
            logger.warning("attempt to disable critical categories: %s", critical_off)
            answer = QMessageBox.warning(
                self, "Предупреждение",
                "Вы отключаете критическую категорию аудита:\n"
                f"{', '.join(critical_off)}\n\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        payload = {
            "audit_categories": selected,
            "audit_retention_days": self.spin_retention.value(),
            "db_pool_size": self.spin_pool_size.value(),
            "db_max_overflow": self.spin_max_overflow.value(),
            "db_pool_recycle": self.spin_pool_recycle.value(),
            "db_pool_timeout": self.spin_pool_timeout.value(),
            "db_echo_sql": self.chk_echo_sql.isChecked(),
            "backup_enabled": self.chk_backup_enabled.isChecked(),
            "backup_hour": self.spin_backup_hour.value(),
            "backup_retention_days": self.spin_backup_retention.value(),
        }
        logger.info(
            "UI: saving settings (categories=%d, retention=%d days)",
            len(selected), self.spin_retention.value(),
        )
        self.btn_save.setEnabled(False)
        self._save_task = run_async(
            lambda: self.api.update_settings(payload),
            on_done=self._on_saved,
            on_error=self._on_save_error,
            parent=self,
        )

    def _on_saved(self, _result):
        self._save_task = None
        self.btn_save.setEnabled(True)
        QMessageBox.information(self, "Готово", "Настройки сохранены")
        self.refresh()

    def _on_save_error(self, exc: Exception):
        self._save_task = None
        self.btn_save.setEnabled(True)
        logger.error("update_settings failed: %s", exc)
        QMessageBox.critical(self, "Ошибка", humanize_api_error(exc))