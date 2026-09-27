import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger("admin_tool.server")


class ServerManager(QObject):
    log_line = Signal(str)
    state_changed = Signal(str)   # stopped | starting | running | stopping | failed

    def __init__(
            self,
            backend_dir: Path,
            host: str = "127.0.0.1",
            port: int = 8000,
            log_dir: Path | None = None,
            *,
            tls_enabled: bool = False,
            tls_cert_file: Path | None = None,
            tls_key_file: Path | None = None,
            tls_ca_file: Path | None = None,
            tls_verify_client: bool = False,
    ):
        super().__init__()
        self.backend_dir = backend_dir
        self.host = host
        self.port = port

        self.log_dir = log_dir or (backend_dir.parent / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "backend.log"
        self.pid_path = self.log_dir / "backend.pid"

        # --- TLS ---
        self.tls_enabled = tls_enabled
        self.tls_cert_file = Path(tls_cert_file) if tls_cert_file else None
        self.tls_key_file = Path(tls_key_file) if tls_key_file else None
        self.tls_ca_file = Path(tls_ca_file) if tls_ca_file else None
        self.tls_verify_client = tls_verify_client

        self._proc: subprocess.Popen | None = None
        self._external_pid: int | None = None
        self._state = "stopped"
        self._lock = threading.Lock()

    # ------------------------------------------------------------- logging

    def _emit(self, msg: str, level: int = logging.INFO) -> None:
        logger.log(level, "%s", msg)
        self.log_line.emit(msg)

    # ------------------------------------------------------------- properties

    @property
    def state(self) -> str:
        return self._state

    @property
    def pid(self) -> int | None:
        if self._proc and self._proc.poll() is None:
            return self._proc.pid
        return self._external_pid

    # ------------------------------------------------------------- port utils

    def is_port_busy(self) -> bool:
        try:
            import psutil

            for connection in psutil.net_connections(kind="tcp"):
                if not connection.laddr:
                    continue

                if connection.laddr.port != self.port:
                    continue

                if connection.status == psutil.CONN_LISTEN:
                    return True

            return False

        except Exception as error:
            logger.warning(
                "не удалось проверить занятость порта %s:%s: %s",
                self.host,
                self.port,
                error
            )
            return False

    def find_port_owner(self) -> dict | None:
        """{'pid': int, 'name': str} владельца порта, либо None."""
        try:
            import psutil  # type: ignore
        except ImportError:
            psutil = None  # type: ignore

        if psutil is not None:
            try:
                for conn in psutil.net_connections(kind="inet"):
                    if conn.status != psutil.CONN_LISTEN:
                        continue
                    if conn.laddr and conn.laddr.port == self.port:
                        if conn.pid:
                            pid = int(conn.pid)
                            return {"pid": pid, "name": self._process_name(pid)}
            except Exception:
                logger.debug("psutil net_connections failed", exc_info=True)

        if sys.platform == "win32":
            return self._find_port_owner_win_netstat()
        return self._find_port_owner_unix()

    def _find_port_owner_win_netstat(self) -> dict | None:
        """Парсит netstat -ano без опоры на слово LISTENING.

        Строка вида:
            TCP  127.0.0.1:8000  0.0.0.0:0  LISTENING  1234
        Порт LISTENING-сокета всегда имеет Foreign Address с портом 0.
        """
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
        except Exception:
            logger.debug("netstat failed", exc_info=True)
            return None

        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            if parts[0].upper() != "TCP":
                continue
            local, foreign = parts[1], parts[2]
            if not foreign.endswith(":0"):
                continue
            if ":" not in local:
                continue
            _, _, port_str = local.rpartition(":")
            try:
                if int(port_str) != self.port:
                    continue
            except ValueError:
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            return {"pid": pid, "name": self._process_name(pid)}
        return None

    def _find_port_owner_unix(self) -> dict | None:
        try:
            out = subprocess.run(
                ["lsof", "-ti", f":{self.port}"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip().splitlines()
            if not out:
                return None
            pid = int(out[0])
            return {"pid": pid, "name": self._process_name(pid)}
        except Exception:
            logger.debug("lsof failed", exc_info=True)
            return None

    @staticmethod
    def _process_name(pid: int) -> str:
        try:
            import psutil  # type: ignore
            return psutil.Process(pid).name()
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout.strip()
                if out.startswith('"'):
                    return out.split('","')[0].strip('"')
            except Exception:
                pass
        return "unknown"

    @staticmethod
    def _process_cmdline(pid: int) -> str | None:
        """Командная строка процесса, если удалось получить."""
        try:
            import psutil  # type: ignore
            return " ".join(psutil.Process(pid).cmdline())
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                out = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={pid}",
                     "get", "CommandLine", "/format:list"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("CommandLine="):
                        return line[len("CommandLine="):]
            except Exception:
                pass
        return None

    def is_process_alive(self, pid: int) -> bool:
        if sys.platform == "win32":
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                return out.startswith('"')
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------- pid file

    def _write_pid(self, pid: int) -> None:
        try:
            self.pid_path.write_text(str(pid), encoding="utf-8")
        except Exception:
            logger.warning("cannot write pid file %s", self.pid_path, exc_info=True)

    def _read_pid(self) -> int | None:
        try:
            if not self.pid_path.exists():
                return None
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _clear_pid(self) -> None:
        try:
            self.pid_path.unlink(missing_ok=True)
        except Exception:
            pass

    def find_running_backend(self) -> int | None:
        pid = self._read_pid()
        if pid and self.is_process_alive(pid):
            return pid
        if pid:
            logger.info("stale pid file (pid=%s dead) — removing", pid)
            self._clear_pid()

        owner = self.find_port_owner()
        if owner:
            name = (owner["name"] or "").lower()
            if name.startswith("python"):
                return owner["pid"]
        return None

    # ------------------------------------------------------------- public API

    def attach(self) -> bool:
        pid = self.find_running_backend()
        if not pid:
            return False
        self._external_pid = pid
        self._set_state("running")
        self._emit(f"[server] подключен к работающему backend PID={pid}")

        start_at = 0
        try:
            start_at = self.log_path.stat().st_size
        except Exception:
            start_at = 0
        threading.Thread(target=self._tail_log, args=(start_at,), daemon=True).start()
        return True

    def start(self) -> bool:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._emit("[server] уже запущен (наш процесс)")
                return True
            if self._external_pid and self.is_process_alive(self._external_pid):
                self._emit("[server] уже запущен (внешний процесс)")
                return True

            if self.is_port_busy():
                owner = self.find_port_owner()
                if owner:
                    self._emit(
                        f"[server] порт {self.host}:{self.port} занят: "
                        f"PID={owner['pid']} ({owner['name']}). "
                        f"Если это осиротевший uvicorn — нажмите «Освободить порт».",
                        logging.WARNING,
                    )
                else:
                    self._emit(
                        f"[server] порт {self.host}:{self.port} занят, "
                        f"владельца определить не удалось.",
                        logging.WARNING,
                    )
                self._set_state("failed")
                return False

            if self.tls_enabled:
                if not self.tls_cert_file or not self.tls_cert_file.exists():
                    self._emit(
                        f"[server] TLS: сертификат не найден: {self.tls_cert_file}",
                        logging.ERROR,
                    )
                    self._set_state("failed")
                    return False
                if not self.tls_key_file or not self.tls_key_file.exists():
                    self._emit(
                        f"[server] TLS: приватный ключ не найден: {self.tls_key_file}",
                        logging.ERROR,
                    )
                    self._set_state("failed")
                    return False
                if self.tls_verify_client and (
                        not self.tls_ca_file or not self.tls_ca_file.exists()
                ):
                    self._emit(
                        f"[server] mTLS: CA-файл не найден: {self.tls_ca_file}",
                        logging.ERROR,
                    )
                    self._set_state("failed")
                    return False

            self._set_state("starting")
            scheme = "https" if self.tls_enabled else "http"
            self._emit(f"[server] запуск uvicorn на {scheme}://{self.host}:{self.port}")

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_backend_log()
            log_fh = open(self.log_path, "ab", buffering=0)

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            env["SSL_ENABLED"] = "true" if self.tls_enabled else "false"
            if self.tls_enabled:
                if self.tls_cert_file:
                    env["SSL_CERT_FILE"] = str(self.tls_cert_file)
                if self.tls_key_file:
                    env["SSL_KEY_FILE"] = str(self.tls_key_file)
                if self.tls_ca_file:
                    env["SSL_CA_FILE"] = str(self.tls_ca_file)
                env["SSL_VERIFY_CLIENT"] = (
                    "true" if self.tls_verify_client else "false"
                )

            cmd = [
                sys.executable, "-m", "app.server",
                "--host", self.host,
                "--port", str(self.port),
            ]

            creationflags = 0
            start_new_session = False
            if sys.platform == "win32":
                creationflags = (
                        subprocess.DETACHED_PROCESS
                        | subprocess.CREATE_NEW_PROCESS_GROUP
                )
                creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
                try:
                    creationflags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
                except AttributeError:
                    pass
            else:
                start_new_session = True

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.backend_dir),
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    creationflags=creationflags,
                    start_new_session=start_new_session,
                )
            except OSError as exc:
                log_fh.close()
                self._set_state("failed")
                self._emit(
                    f"[server] не удалось запустить процесс: {exc}",
                    logging.ERROR,
                )
                logger.exception("uvicorn spawn failed")
                return False

            try:
                log_fh.close()
            except Exception:
                pass

            self._write_pid(self._proc.pid)
            self._emit(f"[server] uvicorn PID={self._proc.pid}")

            try:
                start_at = 0
                if self.log_path.exists():
                    start_at = self.log_path.stat().st_size
            except Exception:
                start_at = 0

            threading.Thread(
                target=self._tail_log, args=(start_at,), daemon=True
            ).start()
            threading.Thread(
                target=self._watchdog, args=(self._proc,), daemon=True
            ).start()
            return True

    def stop(self) -> None:
        threading.Thread(target=self._stop_blocking, daemon=True).start()

    def stop_blocking(self, timeout: float = 8.0) -> None:
        self._stop_blocking()

    def restart(self) -> None:
        threading.Thread(target=self._restart_worker, daemon=True).start()

    def free_port(self) -> bool:
        """Освобождает порт, если его занимает именно наш backend."""
        owner = self.find_port_owner()
        if not owner:
            self._emit("[server] владелец порта не найден", logging.WARNING)
            return False

        name = (owner["name"] or "").lower()
        if not name.startswith("python"):
            self._emit(
                f"[server] порт занимает {owner['name']} (PID {owner['pid']}) — "
                f"это не Python, не трогаем.",
                logging.WARNING,
            )
            return False

        cmdline = self._process_cmdline(owner["pid"]) or ""
        low = cmdline.lower()
        if "uvicorn" not in low and "app.main" not in low:
            self._emit(
                f"[server] PID {owner['pid']} — python, но не наш backend: "
                f"{cmdline[:120] or '(cmdline недоступна)'}. Не трогаем.",
                logging.WARNING,
            )
            return False

        self._emit(
            f"[server] убиваем uvicorn PID={owner['pid']} ({owner['name']})",
            logging.WARNING,
        )

        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(owner["pid"])],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=8,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as exc:
                self._emit(f"[server] taskkill failed: {exc}", logging.ERROR)
                logger.exception("taskkill failed")
                return False
        else:
            try:
                os.kill(owner["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as exc:
                self._emit(f"[server] kill failed: {exc}", logging.ERROR)
                logger.exception("kill failed")
                return False

        for _ in range(20):
            if not self.is_port_busy():
                self._emit("[server] порт освобождён")
                self._clear_pid()
                self._external_pid = None
                return True
            time.sleep(0.2)

        if sys.platform != "win32":
            try:
                os.kill(owner["pid"], signal.SIGKILL)
            except Exception:
                pass
            for _ in range(10):
                if not self.is_port_busy():
                    self._emit("[server] порт освобождён (SIGKILL)")
                    self._clear_pid()
                    self._external_pid = None
                    return True
                time.sleep(0.2)

        self._emit("[server] порт всё ещё занят после убийства", logging.WARNING)
        return False

    # ------------------------------------------------------------- internals

    def _set_state(self, s: str) -> None:
        if s != self._state:
            logger.debug("server state: %s → %s", self._state, s)
        self._state = s
        self.state_changed.emit(s)

    def _stop_blocking(self) -> None:
        with self._lock:
            pid = self.pid
            if not pid:
                self._proc = None
                self._external_pid = None
                self._clear_pid()
                self._set_state("stopped")
                return

            self._set_state("stopping")
            self._emit(f"[server] остановка PID={pid}")

            if sys.platform == "win32":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=8,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                except Exception as exc:
                    self._emit(f"[server] taskkill failed: {exc}", logging.WARNING)
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

            deadline = time.time() + 8
            while time.time() < deadline:
                if not self.is_process_alive(pid):
                    break
                time.sleep(0.2)

            if self._proc:
                try:
                    self._proc.wait(timeout=2)
                except Exception:
                    pass

            self._proc = None
            self._external_pid = None
            self._clear_pid()
            self._set_state("stopped")
            self._emit("[server] остановлен")

    def _restart_worker(self) -> None:
        self._stop_blocking()
        self._wait_port_free(timeout=15)
        if not self.start():
            self._emit("[server] первая попытка старта не удалась — ждём",
                       logging.WARNING)
            time.sleep(2.0)
            self._wait_port_free(timeout=10)
            self.start()

    def _wait_port_free(self, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_port_busy():
                waited = timeout - (deadline - time.time())
                self._emit(f"[server] порт свободен через {waited:.1f} сек")
                return
            time.sleep(0.2)
        self._emit(f"[server] порт всё ещё занят после {timeout} сек ожидания",
                   logging.WARNING)

    def _tail_log(self, start_at: int = 0) -> None:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(start_at)
                while True:
                    line = f.readline()
                    if line:
                        self.log_line.emit(line.rstrip())
                        logger.debug("backend: %s", line.rstrip())
                        continue
                    if not self._is_alive_for_tail():
                        break
                    time.sleep(0.3)
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("tail_log failed")

    def _is_alive_for_tail(self) -> bool:
        if self._proc and self._proc.poll() is None:
            return True
        if self._external_pid and self.is_process_alive(self._external_pid):
            return True
        return False

    def _watchdog(self, proc: subprocess.Popen) -> None:
        def _handle_dead(rc: int | None) -> None:
            self._set_state("failed")
            self._clear_pid()
            with self._lock:
                if self._proc is proc:
                    self._proc = None
            self._emit(
                f"[server] процесс завершился с кодом {rc}.",
                logging.ERROR,
            )

        time.sleep(1.5)
        if self._proc is not proc:
            return
        rc = proc.poll()
        if rc is not None:
            _handle_dead(rc)
            return
        self._set_state("running")

        while True:
            time.sleep(2.0)
            if self._proc is not proc:
                return
            rc = proc.poll()
            if rc is not None:
                _handle_dead(rc)
                return
                
    def _rotate_backend_log(self) -> None:
        if not self.log_path.exists():
            return

        history_dir = self.log_path.parent / "backend_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        archive_path = history_dir / f"backend_{timestamp}.log"

        try:
            self.log_path.rename(archive_path)
        except Exception:
            logger.exception("не удалось переместить старый backend.log")
            return

        archives = sorted(
            history_dir.glob("backend_*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        for old_log in archives[10:]:
            try:
                old_log.unlink()
            except Exception:
                logger.warning(
                    "не удалось удалить старый backend log: %s",
                    old_log,
                )