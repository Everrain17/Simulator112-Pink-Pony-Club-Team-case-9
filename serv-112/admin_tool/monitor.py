import logging
import time

import psutil
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal


logger = logging.getLogger("admin_tool.monitor")


class _HealthSignals(QObject):
    # Обновленный Qt-сигнал на 5 параметров состояния
    result = Signal(bool, bool, bool, bool, bool)


class _HealthTask(QRunnable):


    def __init__(self, api, signals: _HealthSignals):
        super().__init__()
        self.api = api
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        api_ok = False
        redis_ok = False
        simcore_ok = False
        tts_ok = False
        qwen_ok = False
        
        try:
            h = self.api.healthz(timeout=1.5)
            api_ok = True
            redis_ok = bool(h.get("redis"))
            
            # Запрашиваем информацию о состоянии компонентов с Python бэкенда
            sys_info = self.api.system_info()
            simcore_ok = sys_info.get("simcore_ok", False)
            tts_ok = sys_info.get("tts_ok", False)
            qwen_ok = sys_info.get("qwen_ok", False)
        except Exception:
            pass
            
        try:
            self.signals.result.emit(api_ok, redis_ok, simcore_ok, tts_ok, qwen_ok)
        except RuntimeError:
            pass


class Monitor(QObject):
    metrics = Signal(dict)


    POLL_INTERVAL_MS = 5000

    def __init__(self, server_manager, api_client, interval_ms: int | None = None):
        super().__init__()
        self.sm = server_manager
        self.api = api_client
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms or self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._last_api_ok: bool | None = None
        self._last_redis_ok: bool | None = None

        self._pool = QThreadPool.globalInstance()
        self._inflight = False
        self._pending: dict | None = None
        self._signals = _HealthSignals()
        self._signals.result.connect(self._on_health)

    def start(self) -> None:
        self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._timer.stop()
        self._pending = None



    def _tick(self) -> None:
        if self._inflight:
            return

        data = {
            "state": self.sm.state,
            "pid": self.sm.pid,
            "cpu": 0.0,
            "ram_mb": 0.0,
            "uptime": 0,
            "redis_ok": False,
            "api_ok": False,
            "simcore_ok": False,
            "tts_ok": False,
            "qwen_ok": False,
        }

        if self.sm.pid:
            self._fill_process_metrics(data, self.sm.pid)

        self._pending = data
        self._inflight = True
        self._pool.start(_HealthTask(self.api, self._signals))

    def _on_health(self, api_ok: bool, redis_ok: bool, simcore_ok: bool, tts_ok: bool, qwen_ok: bool) -> None:
        self._inflight = False
        data = self._pending
        self._pending = None
        if data is None:
            return

        data["api_ok"] = api_ok
        data["redis_ok"] = redis_ok
        data["simcore_ok"] = simcore_ok
        data["tts_ok"] = tts_ok
        data["qwen_ok"] = qwen_ok

        self._log_transitions(data)
        self.metrics.emit(data)

    def _log_transitions(self, data: dict) -> None:
        if self._last_api_ok is not None and self._last_api_ok != data["api_ok"]:
            if data["api_ok"]:
                logger.info("API health restored")
            else:
                logger.warning("API health lost")
        self._last_api_ok = data["api_ok"]

        if self._last_redis_ok is not None and self._last_redis_ok != data["redis_ok"]:
            if data["redis_ok"]:
                logger.info("Redis health restored")
            else:
                logger.warning("Redis health lost")
        self._last_redis_ok = data["redis_ok"]

    def _fill_process_metrics(self, data: dict, pid: int) -> None:
        try:
            p = psutil.Process(pid)
            procs = [p] + p.children(recursive=True)

            data["uptime"] = int(time.time() - p.create_time())

            cpu = 0.0
            ram = 0
            for pr in procs:
                try:
                    cpu += pr.cpu_percent(interval=None)
                    ram += pr.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            data["cpu"] = round(cpu, 1)
            data["ram_mb"] = round(ram / 1024 / 1024, 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
