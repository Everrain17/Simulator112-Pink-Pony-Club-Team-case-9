"""Минимальный помощник для фоновых задач.

Позволяет запустить блокирующий вызов (API, файлы, subprocess) в
QThreadPool и получить результат слотом в GUI-потоке. Возвращаемый
AsyncTask можно отменить — тогда finished/failed не сработают, даже
если задача уже выполнилась.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


logger = logging.getLogger("admin_tool.async_utils")


class AsyncTask(QObject):
    finished = Signal(object)   # результат
    failed = Signal(Exception)  # исключение

    def __init__(self, fn: Callable[[], Any], parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class _Runner(QRunnable):
    def __init__(self, task: AsyncTask):
        super().__init__()
        self.task = task
        self.setAutoDelete(True)

    def run(self) -> None:
        task = self.task
        try:
            result = task._fn()
        except Exception as exc:
            logger.debug("async task failed: %s", exc)
            if not task.cancelled:
                try:
                    task.failed.emit(exc)
                except RuntimeError:
                    pass
            return
        except BaseException:
            sys.excepthook(*sys.exc_info())
            if not task.cancelled:
                try:
                    task.failed.emit(RuntimeError("внутренняя ошибка задачи"))
                except RuntimeError:
                    pass
            return
        if not task.cancelled:
            try:
                task.finished.emit(result)
            except RuntimeError:
                pass


def run_async(
    fn: Callable[[], Any],
    *,
    on_done: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    parent: QObject | None = None,
) -> AsyncTask:
    """Запускает fn() в QThreadPool. Колбэки — в GUI-потоке.

    parent задаёт владельца AsyncTask (обычно виджет): при его удалении
    сигналы отвяжутся автоматически.
    """
    task = AsyncTask(fn, parent=parent)
    task.finished.connect(on_done)
    task.failed.connect(on_error)
    QThreadPool.globalInstance().start(_Runner(task))
    return task