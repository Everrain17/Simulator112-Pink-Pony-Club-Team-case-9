import os
import sys
import signal
import subprocess
import time


# =========================================================
# ROOT
# Всегда папка, где находится System112.exe
# =========================================================

if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(
        os.path.abspath(sys.executable)
    )
else:
    ROOT = os.path.dirname(
        os.path.abspath(__file__)
    )


LOGS_DIR = os.path.join(
    ROOT,
    "Logs"
)


# =========================================================
# PATHS
# =========================================================

QWEN_DIR = os.path.join(
    ROOT,
    "llama-b8665-bin-win-cuda-13.1-x64"
)

QWEN_EXE = os.path.join(
    QWEN_DIR,
    "llama-server.exe"
)

TTS_DIR = os.path.join(
    ROOT,
    "tts-server"
)

TTS_ACTIVATE = os.path.join(
    TTS_DIR,
    "venv",
    "Scripts",
    "activate.bat"
)

TTS_SCRIPT = os.path.join(
    TTS_DIR,
    "tts_server.py"
)

ADMIN_DIR = os.path.join(
    ROOT,
    "serv-112"
)

ADMIN_ACTIVATE = os.path.join(
    ADMIN_DIR,
    ".venv",
    "Scripts",
    "activate.bat"
)

ADMIN_MAIN = os.path.join(
    ADMIN_DIR,
    "admin_tool",
    "main.py"
)

BACKEND_PID_FILE = os.path.join(
    ADMIN_DIR,
    "logs",
    "backend.pid"
)


# =========================================================
# PROCESSES
# =========================================================

processes = []
_stopping = False


def create_logs():
    os.makedirs(
        LOGS_DIR,
        exist_ok=True
    )


def open_log(name):
    return open(
        os.path.join(
            LOGS_DIR,
            name
        ),
        "a",
        encoding="utf-8",
        errors="replace"
    )


def write_system(message):
    with open_log(
        "system.log"
    ) as log:
        log.write(
            message + "\n"
        )
        log.flush()


def child_environment():
    """Не даём прокси/VPN перехватывать локальные localhost-запросы."""

    env = os.environ.copy()

    no_proxy_values = [
        value.strip()
        for value in env.get("NO_PROXY", "").split(",")
        if value.strip()
    ]

    for value in [
        "127.0.0.1",
        "localhost",
    ]:
        if value not in no_proxy_values:
            no_proxy_values.append(value)

    env["NO_PROXY"] = ",".join(no_proxy_values)
    env["no_proxy"] = env["NO_PROXY"]

    return env


def start_process(
    name,
    command,
    cwd,
    log_name
):
    write_system(
        f"[START] {name}"
    )

    write_system(
        f"[CWD] {cwd}"
    )

    write_system(
        f"[COMMAND] {command}"
    )

    log = open_log(
        log_name
    )

    log.write(
        f"\n\n========== START {name} ==========\n"
    )
    log.flush()

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=child_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    except Exception as error:

        log.write(
            "\n========== START ERROR ==========\n"
        )

        log.write(
            repr(error)
        )

        log.write("\n")
        log.flush()
        log.close()

        write_system(
            f"[ERROR] {name}: {repr(error)}"
        )

        raise

    processes.append(
        {
            "name": name,
            "process": process,
            "log": log,
        }
    )

    write_system(
        f"[OK] {name} PID={process.pid}"
    )

    return process


def taskkill_tree(pid):
    if not pid:
        return

    try:
        subprocess.run(
            [
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )

    except Exception as error:
        write_system(
            f"[WARN] taskkill PID={pid}: {repr(error)}"
        )


def read_backend_pid():
    try:
        if not os.path.exists(BACKEND_PID_FILE):
            return None

        with open(
            BACKEND_PID_FILE,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as file:
            value = file.read().strip()

        pid = int(value)

        if pid <= 0:
            return None

        return pid

    except Exception as error:
        write_system(
            f"[WARN] backend.pid read failed: {repr(error)}"
        )
        return None


def kill_backend_process():
    pid = read_backend_pid()

    if pid is None:
        return

    write_system(
        f"[STOP] Backend PID from backend.pid: {pid}"
    )

    taskkill_tree(pid)


def stop_all():
    global _stopping

    if _stopping:
        return

    _stopping = True

    write_system(
        "[STOP] Остановка всех компонентов"
    )

    # Сначала Admin Tool, затем его detached backend.
    for item in reversed(processes):

        write_system(
            f"[STOP] {item['name']} PID={item['process'].pid}"
        )

        taskkill_tree(
            item["process"].pid
        )

    kill_backend_process()

    for item in processes:

        try:
            item["log"].write(
                f"\n========== STOP {item['name']} ==========\n"
            )

            item["log"].flush()
            item["log"].close()

        except Exception:
            pass

    processes.clear()


def shutdown_handler(signum, frame):
    stop_all()
    sys.exit(0)


# =========================================================
# VALIDATION
# =========================================================

def validate():

    write_system(
        "[CHECK] Проверка файлов"
    )

    required = [
        (
            "Qwen",
            QWEN_EXE
        ),
        (
            "TTS activate",
            TTS_ACTIVATE
        ),
        (
            "TTS server",
            TTS_SCRIPT
        ),
        (
            "Admin activate",
            ADMIN_ACTIVATE
        ),
        (
            "Admin main",
            ADMIN_MAIN
        ),
    ]

    for name, path in required:

        if not os.path.exists(path):

            write_system(
                f"[MISSING] {name}: {path}"
            )

            return False

        write_system(
            f"[FOUND] {name}: {path}"
        )

    return True


# =========================================================
# DOTNET
# =========================================================

def find_dotnet():

    try:

        result = subprocess.run(
            [
                "where",
                "dotnet",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )

        if result.returncode != 0:
            return "dotnet"

        paths = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

        if paths:
            return paths[0]

    except Exception:
        pass

    return "dotnet"


# =========================================================
# MAIN
# =========================================================

def main():

    signal.signal(
        signal.SIGINT,
        shutdown_handler
    )

    signal.signal(
        signal.SIGTERM,
        shutdown_handler
    )

    create_logs()

    write_system(
        "\n=========================================="
    )

    write_system(
        "SYSTEM112 PRODUCTION LAUNCHER START"
    )

    write_system(
        f"ROOT: {ROOT}"
    )

    write_system(
        f"EXE: {sys.executable}"
    )

    write_system(
        "=========================================="
    )

    if not validate():
        return 1

    try:

        # =================================================
        # 1. QWEN
        # =================================================

        qwen = start_process(
            "QWEN",
            [
                QWEN_EXE,
                "-m",
                "Qwen3.5-9B-Q4_K_S.gguf",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
                "--reasoning",
                "off",
                "-ngl",
                "99",
                "-b",
                "512",
                "--no-cache-prompt",
            ],
            QWEN_DIR,
            "qwen.log",
        )

        # =================================================
        # 2. TTS
        # =================================================

        tts = start_process(
            "TTS SERVER",
            [
                os.environ.get(
                    "COMSPEC",
                    "cmd.exe"
                ),
                "/c",
                "call venv\\Scripts\\activate.bat & python tts_server.py",
            ],
            TTS_DIR,
            "tts.log",
        )

        # =================================================
        # 3. C# BACKEND
        # =================================================

        dotnet = find_dotnet()

        write_system(
            f"[DOTNET] {dotnet}"
        )

        csharp = start_process(
            "C# BACKEND",
            [
                dotnet,
                "run",
            ],
            ROOT,
            "csharp.log",
        )

        # =================================================
        # 4. ADMIN TOOL
        # =================================================

        admin = start_process(
            "ADMIN TOOL",
            [
                os.environ.get(
                    "COMSPEC",
                    "cmd.exe"
                ),
                "/c",
                "call .venv\\Scripts\\activate.bat & python -m admin_tool.main",
            ],
            ADMIN_DIR,
            "admin.log",
        )

        write_system(
            "=========================================="
        )

        write_system(
            "Все компоненты отправлены на запуск."
        )

        write_system(
            f"Qwen PID: {qwen.pid}"
        )

        write_system(
            f"TTS PID: {tts.pid}"
        )

        write_system(
            f"C# PID: {csharp.pid}"
        )

        write_system(
            f"Admin Tool CMD PID: {admin.pid}"
        )

        write_system(
            "=========================================="
        )

        # =================================================
        # Ждём завершения Admin Tool CMD
        # =================================================

        write_system(
            "[WAIT] Ожидание закрытия Admin Tool..."
        )

        while True:

            result = admin.poll()

            if result is not None:

                write_system(
                    f"Admin Tool завершён. Код: {result}"
                )

                break

            time.sleep(0.5)

    except Exception as error:

        write_system(
            "=========================================="
        )

        write_system(
            "[CRITICAL ERROR]"
        )

        write_system(
            repr(error)
        )

        write_system(
            "=========================================="
        )

        return 1

    finally:

        stop_all()

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
