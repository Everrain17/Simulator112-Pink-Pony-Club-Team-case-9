import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


logger = logging.getLogger("admin_tool.docker")


class DockerManager(QObject):
    log_line = Signal(str)           # строки для лога
    status_changed = Signal(dict)    # {"docker_running": bool, "services": {name: {...}}}

    POLL_INTERVAL_MS = 3000

    def __init__(self, project_dir: Path, compose_file: str = "docker-compose.yml"):
        super().__init__()
        self.project_dir = project_dir
        self.compose_file = compose_file
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._schedule_probe)
        self._probe_inflight = False
        self._polling_active = False
        self._lock = threading.Lock()
        self._last_probe_ok: bool | None = None

    # ------------------------------------------------------------- logging

    def _emit(self, msg: str, level: int = logging.INFO) -> None:
        logger.log(level, "%s", msg)
        self.log_line.emit(msg)

    # ------------------------------------------------------------- polling

    def start_polling(self):
        self._polling_active = True
        self._timer.start()
        self._schedule_probe()

    def stop_polling(self):
        self._polling_active = False
        self._timer.stop()

    def _schedule_probe(self):
        if self._probe_inflight:
            return
        self._probe_inflight = True
        threading.Thread(target=self._probe_worker, daemon=True).start()

    def _probe_worker(self):
        try:
            status = self._collect_status()
        except Exception as exc:
            logger.exception("docker probe failed")
            status = {"docker_running": False, "services": {}, "error": str(exc)}
        self._probe_inflight = False

        if not self._polling_active:
            return

        self.status_changed.emit(status)

        now_ok = bool(status.get("docker_running"))
        if self._last_probe_ok is not None and self._last_probe_ok != now_ok:
            if now_ok:
                logger.info("docker engine became available")
            else:
                logger.warning("docker engine became unavailable")
        self._last_probe_ok = now_ok

    def _collect_status(self) -> dict:
        if not self._docker_running():
            return {"docker_running": False, "services": {}}

        out = self._run(
            ["docker", "compose", "-f", self.compose_file, "ps", "--format", "json"],
            timeout=10,
            check=False,
        )
        services = self._parse_ps(out)
        return {"docker_running": True, "services": services}

    # -------------------------------------------------------- docker status

    def _docker_running(self) -> bool:
        """Проверяет, что CLI есть и engine отвечает.

        Различает три случая:
          - CLI не установлен       → debug, вернём False;
          - CLI есть, engine молчит → debug, вернём False;
          - всё ок                  → True.
        """
        try:
            r = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
            )
        except FileNotFoundError:
            logger.debug("docker CLI not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            logger.debug("docker info timed out")
            return False
        except Exception:
            logger.debug("docker info failed", exc_info=True)
            return False

        if r.returncode != 0:
            logger.debug(
                "docker info exit=%d stderr=%s",
                r.returncode, (r.stderr or "").strip()[:200],
            )
            return False
        return r.stdout.strip() != ""

    def _parse_ps(self, raw: str) -> dict:
        raw = raw.strip()
        if not raw:
            return {}

        items: list[dict] = []
        if raw.startswith("["):
            try:
                items = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("compose ps: malformed JSON array", exc_info=True)
                items = []
        else:
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        result: dict[str, dict] = {}
        for it in items:
            name = it.get("Service") or it.get("Name") or "unknown"
            result[name] = {
                "name":     it.get("Name", name),
                "state":    (it.get("State") or "").lower(),
                "status":   it.get("Status", ""),
                "health":   (it.get("Health") or "").lower(),
                "ports":    it.get("Publishers") or it.get("Ports") or [],
            }
        return result

    # ------------------------------------------------------------- operations

    def up(self):
        self._run_async("up", ["docker", "compose", "-f", self.compose_file, "up", "-d"])

    def down(self):
        self._run_async("down", ["docker", "compose", "-f", self.compose_file, "down"])

    def restart(self):
        self._run_async("restart", ["docker", "compose", "-f", self.compose_file, "restart"])

    def pull(self):
        self._run_async("pull", ["docker", "compose", "-f", self.compose_file, "pull"])

    def _run_async(self, label: str, cmd: list[str]):
        threading.Thread(target=self._run_worker, args=(label, cmd), daemon=True).start()

    def _run_worker(self, label: str, cmd: list[str]):
        with self._lock:
            self._emit(f"[docker] {label}: {' '.join(cmd)}")
            try:
                r = subprocess.run(
                    cmd,
                    cwd=str(self.project_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                    creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
                )
            except subprocess.TimeoutExpired:
                self._emit(f"[docker] {label}: timeout", logging.ERROR)
                return
            except FileNotFoundError:
                self._emit("[docker] docker не найден в PATH", logging.ERROR)
                return

            if r.stdout:
                for line in r.stdout.rstrip().splitlines():
                    self._emit(f"  {line}")
            if r.stderr:
                for line in r.stderr.rstrip().splitlines():
                    self._emit(f"  {line}", logging.WARNING)

            level = logging.INFO if r.returncode == 0 else logging.ERROR
            self._emit(
                f"[docker] {label}: {'ok' if r.returncode == 0 else f'failed ({r.returncode})'}",
                level,
            )
            self._schedule_probe()

    # ------------------------------------------------------------- utils

    def _run(self, cmd: list[str], timeout: int = 10, check: bool = True) -> str:
        r = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
        )
        if check and r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"exit {r.returncode}")
        return r.stdout

    # ------------------------------------------------------------- public checks

    def is_docker_running(self, timeout: int = 3) -> bool:
        """Публичная проверка: Docker Desktop/engine доступен?"""
        try:
            r = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
            )
            return r.returncode == 0 and r.stdout.strip() != ""
        except Exception:
            return False

    # ------------------------------------------------------ docker desktop search

    def _find_docker_desktop_paths(self) -> list[Path]:
        """Возвращает упорядоченный список кандидатов на Docker Desktop.

        Windows: env-переменные + реестр.
        macOS:   /Applications + ~/Applications + Spotlight.
        """
        candidates: list[Path] = []

        if sys.platform == "win32":
            env_map = [
                ("ProgramFiles",      r"Docker\Docker\Docker Desktop.exe"),
                ("ProgramFiles(x86)", r"Docker\Docker\Docker Desktop.exe"),
                ("ProgramW6432",      r"Docker\Docker\Docker Desktop.exe"),
                ("LOCALAPPDATA",      r"Programs\Docker\Docker\Docker Desktop.exe"),
                ("LOCALAPPDATA",      r"Docker\Docker Desktop.exe"),
                ("ProgramData",       r"DockerDesktop\Docker Desktop.exe"),
            ]
            for env_var, subpath in env_map:
                base = os.environ.get(env_var)
                if base:
                    candidates.append(Path(base) / subpath)

            candidates.extend(self._docker_desktop_from_registry_win())

        elif sys.platform == "darwin":
            candidates.append(Path("/Applications/Docker.app"))
            candidates.append(Path.home() / "Applications" / "Docker.app")
            try:
                out = subprocess.run(
                    ["mdfind",
                     "kMDItemCFBundleIdentifier == 'com.docker.docker'"],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip().splitlines()
                for line in out:
                    p = Path(line.strip())
                    if p.exists() and p not in candidates:
                        candidates.append(p)
            except Exception:
                logger.debug("mdfind for Docker.app failed", exc_info=True)

        seen: set[str] = set()
        unique: list[Path] = []
        for p in candidates:
            key = str(p).lower() if sys.platform == "win32" else str(p)
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        return unique

    @staticmethod
    def _docker_desktop_from_registry_win() -> list[Path]:
        """Ищет путь установки Docker Desktop в реестре Windows."""
        if sys.platform != "win32":
            return []
        try:
            import winreg  # type: ignore
        except ImportError:
            return []

        results: list[Path] = []
        hives = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Docker Inc.\Docker"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Docker Inc.\Docker"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Docker Inc.\Docker"),
        ]
        for hive, subkey in hives:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    for value_name in ("AppPath", "InstallPath", "Path"):
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                        except FileNotFoundError:
                            continue
                        if not value:
                            continue
                        p = Path(str(value))
                        if p.is_file():
                            results.append(p)
                        elif p.is_dir():
                            results.append(p / "Docker Desktop.exe")
            except FileNotFoundError:
                continue
            except Exception:
                logger.debug("registry read failed hive=%s key=%s",
                             hive, subkey, exc_info=True)
        return results

    # ------------------------------------------------------------- docker

    def try_start_docker_desktop(self) -> bool:
        """Попытка запустить Docker Desktop на Windows/macOS.

        Возвращает True, если команда запуска отправлена (engine поднимается
        20–40 секунд, сразу после возврата он ещё не готов).
        """
        candidates = self._find_docker_desktop_paths()

        if not candidates:
            logger.warning("no Docker Desktop install paths to try")
            self._emit(
                "[docker] не удалось определить путь к Docker Desktop. "
                "Проверьте установку вручную.",
                logging.WARNING,
            )
            return False

        tried: list[str] = []
        for path in candidates:
            tried.append(str(path))
            if not path.exists():
                continue

            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    creationflags = (
                        subprocess.DETACHED_PROCESS
                        | subprocess.CREATE_NEW_PROCESS_GROUP
                        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                    subprocess.Popen(
                        [str(path)],
                        creationflags=creationflags,
                        close_fds=True,
                    )
                self._emit(f"[docker] запускаем {path}")
                logger.info("Docker Desktop spawn requested: %s", path)
                return True
            except Exception as exc:
                self._emit(
                    f"[docker] не удалось запустить {path}: {exc}",
                    logging.ERROR,
                )
                logger.exception("failed to spawn Docker Desktop at %s", path)
                return False

        logger.warning(
            "Docker Desktop executable not found. Checked paths:\n  %s",
            "\n  ".join(tried),
        )
        self._emit(
            "[docker] Docker Desktop не найден по стандартным путям. "
            "Запустите вручную (проверенные пути — в admin_tool.log).",
            logging.WARNING,
        )
        return False

    # ------------------------------------------------------------- compose

    def is_compose_healthy(self, timeout: int = 5) -> bool:
        if not self.is_docker_running(timeout=3):
            return False

        try:
            r = subprocess.run(
                ["docker", "compose", "-f", self.compose_file,
                 "ps", "--format", "json"],
                cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
            )
        except Exception:
            return False

        if r.returncode != 0:
            return False

        services = self._parse_ps(r.stdout)
        if not services:
            return False

        for info in services.values():
            state = (info.get("state") or "").lower()
            health = (info.get("health") or "").lower()
            if state != "running":
                return False
            if health == "unhealthy":
                return False
        return True

    def compose_up_blocking(self, timeout: int = 120) -> bool:
        self._emit(f"[docker] up: docker compose -f {self.compose_file} up -d")
        try:
            r = subprocess.run(
                ["docker", "compose", "-f", self.compose_file, "up", "-d"],
                cwd=str(self.project_dir),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if self._is_windows() else 0,
            )
        except subprocess.TimeoutExpired:
            self._emit("[docker] up: timeout", logging.ERROR)
            return False
        except FileNotFoundError:
            self._emit("[docker] docker не найден в PATH", logging.ERROR)
            return False

        for line in (r.stdout or "").splitlines():
            self._emit(f"  {line}")
        for line in (r.stderr or "").splitlines():
            self._emit(f"  {line}", logging.WARNING)

        ok = r.returncode == 0
        self._emit(f"[docker] up: {'ok' if ok else f'failed ({r.returncode})'}",
                   logging.INFO if ok else logging.ERROR)
        return ok

    @staticmethod
    def _is_windows() -> bool:
        return sys.platform == "win32"