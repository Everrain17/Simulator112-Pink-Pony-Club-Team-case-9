@echo off
setlocal EnableExtensions EnableDelayedExpansion

title System112 - Setup

REM ==========================================================
REM ROOT DIRECTORIES
REM ==========================================================
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
set "SERVER_DIR=%ROOT_DIR%serv-112"
set "BACKEND_DIR=%SERVER_DIR%\backend"
set "VENV_DIR=%SERVER_DIR%\.venv"

echo.
echo ==========================================
echo System112 - Setup
echo ==========================================
echo Project root: %ROOT_DIR%
echo.

if not exist "%SERVER_DIR%" (
    echo ERROR: serv-112 directory was not found.
    pause
    exit /b 1
)

if not exist "%BACKEND_DIR%" (
    echo ERROR: backend directory was not found.
    pause
    exit /b 1
)

REM ==========================================================
REM 1. CHECK / INSTALL PYTHON
REM ==========================================================
echo [1/7] Checking Python environment...
echo.

set "SYSTEM_PYTHON="

REM ----------------------------------------------------------
REM Try existing python command
REM ----------------------------------------------------------
python --version >nul 2>nul

if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
        set "SYSTEM_PYTHON=%%P"
    )
)

REM ----------------------------------------------------------
REM Try Python Launcher
REM ----------------------------------------------------------
if not defined SYSTEM_PYTHON (
    py -3 --version >nul 2>nul

    if not errorlevel 1 (
        for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
            set "SYSTEM_PYTHON=%%P"
        )
    )
)

REM ----------------------------------------------------------
REM Search common Python installation locations
REM ----------------------------------------------------------
if not defined SYSTEM_PYTHON (
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "SYSTEM_PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe"
    )
)

if not defined SYSTEM_PYTHON (
    if exist "%ProgramFiles%\Python311\python.exe" (
        set "SYSTEM_PYTHON=%ProgramFiles%\Python311\python.exe"
    )
)

if not defined SYSTEM_PYTHON (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "SYSTEM_PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
    )
)

if not defined SYSTEM_PYTHON (
    if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
        set "SYSTEM_PYTHON=%LocalAppData%\Programs\Python\Python313\python.exe"
    )
)

REM ----------------------------------------------------------
REM Install Python if necessary
REM ----------------------------------------------------------
if not defined SYSTEM_PYTHON (

    echo Python was not found.
    echo.
    echo Installing Python 3.11.9...
    echo.

    set "PYTHON_VERSION=3.11.9"
    set "PYTHON_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
    set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"

    REM Remove old installer
    if exist "%PYTHON_INSTALLER%" (
        del /f /q "%PYTHON_INSTALLER%" >nul 2>nul
    )

    echo Downloading Python installer...
    echo.

    REM ------------------------------------------------------
    REM Use Windows BITS instead of Invoke-WebRequest
    REM ------------------------------------------------------
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference='Stop'; Start-BitsTransfer -Source '%PYTHON_URL%' -Destination '%PYTHON_INSTALLER%' -ErrorAction Stop"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to download Python installer.
        echo.
        pause
        exit /b 1
    )

    if not exist "%PYTHON_INSTALLER%" (
        echo.
        echo ERROR: Python installer was not downloaded.
        echo.
        pause
        exit /b 1
    )

    echo Python installer downloaded successfully.
    echo.
    echo Installing Python 3.11.9...
    echo.

    REM


------------------------------------------------------
    REM Install for current user
    REM ------------------------------------------------------
    "%PYTHON_INSTALLER%" ^
        /quiet ^
        InstallAllUsers=0 ^
        PrependPath=1 ^
        Include_test=0 ^
        Include_pip=1 ^
        Include_launcher=1

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install Python.
        echo.
        pause
        exit /b 1
    )

    REM ------------------------------------------------------
    REM Remove installer
    REM ------------------------------------------------------
    del /f /q "%PYTHON_INSTALLER%" >nul 2>nul

    REM ------------------------------------------------------
    REM Refresh PATH
    REM ------------------------------------------------------
    set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"

    REM ------------------------------------------------------
    REM Find newly installed Python
    REM ------------------------------------------------------
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "SYSTEM_PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe"
    )

    if not defined SYSTEM_PYTHON (
        if exist "%ProgramFiles%\Python311\python.exe" (
            set "SYSTEM_PYTHON=%ProgramFiles%\Python311\python.exe"
        )
    )

    if not defined SYSTEM_PYTHON (
        python --version >nul 2>nul

        if not errorlevel 1 (
            for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
                set "SYSTEM_PYTHON=%%P"
            )
        )
    )

    if not defined SYSTEM_PYTHON (
        py -3 --version >nul 2>nul

        if not errorlevel 1 (
            for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
                set "SYSTEM_PYTHON=%%P"
            )
        )
    )
)

REM ----------------------------------------------------------
REM Final Python check
REM ----------------------------------------------------------
if not defined SYSTEM_PYTHON (
    echo.
    echo ERROR: Python was not found after installation.
    echo.
    pause
    exit /b 1
)

echo System Python:
echo %SYSTEM_PYTHON%
echo.

"%SYSTEM_PYTHON%" --version

if errorlevel 1 (
    echo.
    echo ERROR: Python executable cannot be started.
    echo.
    pause
    exit /b 1
)

REM ==========================================================
REM CHECK / REPAIR VIRTUAL ENVIRONMENT
REM ==========================================================
echo.
echo Checking Python virtual environment...
echo.

if not exist "%VENV_DIR%\Scripts\python.exe" (
    goto CREATE_VENV
)

echo Existing virtual environment found.
echo Testing environment...

"%VENV_DIR%\Scripts\python.exe" --version >nul 2>nul

if not errorlevel 1 (
    goto PYTHON_READY
)

REM ----------------------------------------------------------
REM Repair broken virtual environment
REM ----------------------------------------------------------
echo Existing environment is broken.
echo Attempting to repair pyvenv.cfg...
echo.

if exist "%VENV_DIR%\pyvenv.cfg" (

    "%SYSTEM_PYTHON%" -c "from pathlib import Path; import sys; p=Path(r'%VENV_DIR%\pyvenv.cfg'); lines=p.read_text(encoding='utf-8').splitlines(); home=str(Path(sys.executable).parent); found=False; out=[]; [(out.append('home = '+home), globals().update(found=True)) if x.strip().lower().startswith('home =') else out.append(x) for x in lines]; out.insert(0,'home = '+home) if not found else None; p.write_text(chr(10).join(out)+chr(10),encoding='utf-8')"

    if errorlevel 1 (
        echo Failed to repair pyvenv.cfg.
    ) else (
        echo pyvenv.cfg repaired.
    )

) else (
    echo pyvenv.cfg was not found.
)

REM ----------------------------------------------------------
REM Test repaired environment
REM ----------------------------------------------------------
echo Testing repaired environment...

"%VENV_DIR%\Scripts\python.exe" --version >nul 2>nul

if not errorlevel 1 (
    echo Existing


environment repaired successfully.
    goto PYTHON_READY
)

REM ----------------------------------------------------------
REM Repair failed - recreate environment
REM ----------------------------------------------------------
echo.
echo Virtual environment repair failed.
echo Recreating virtual environment...
echo.

if exist "%VENV_DIR%" (
    rmdir /s /q "%VENV_DIR%"
)

goto CREATE_VENV

:CREATE_VENV

echo Creating new Python virtual environment...
echo.

"%SYSTEM_PYTHON%" -m venv "%VENV_DIR%"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment.
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo ERROR: Virtual environment was not created correctly.
    echo.
    pause
    exit /b 1
)

:PYTHON_READY

echo.
echo Python environment OK.
echo.

REM ==========================================================
REM 2. CHECK PYTHON DEPENDENCIES
REM ==========================================================
echo [2/7] Checking Python dependencies...
echo.

if not exist "%BACKEND_DIR%\requirements.txt" (
    echo.
    echo ERROR: requirements.txt was not found.
    echo.
    pause
    exit /b 1
)

echo Updating pip...

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo ERROR: Failed to update pip.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing Python dependencies...
echo.

"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python dependencies.
    echo.
    pause
    exit /b 1
)

echo.
echo Python dependencies OK.
echo.

REM ==========================================================
REM 3. CHECK ALEMBIC
REM ==========================================================
echo [3/7] Checking Alembic...
echo.

if not exist "%BACKEND_DIR%\alembic.ini" (
    echo.
    echo ERROR: alembic.ini was not found.
    echo.
    pause
    exit /b 1
)

cd /d "%BACKEND_DIR%"

"%VENV_DIR%\Scripts\python.exe" -m alembic --version >nul 2>nul

if errorlevel 1 (
    echo Alembic was not found.
    echo Reinstalling backend dependencies...

    "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install Alembic.
        echo.
        pause
        exit /b 1
    )
)

echo Alembic OK.
echo.

REM ==========================================================
REM 4. CHECK DOCKER
REM ==========================================================
echo [4/7] Checking Docker...
echo.

where docker >nul 2>nul

if errorlevel 1 (
    echo.
    echo ERROR: Docker was not found.
    echo Please install Docker Desktop.
    echo.
    pause
    exit /b 1
)

docker --version

if errorlevel 1 (
    echo.
    echo ERROR: Docker command is not working.
    echo.
    pause
    exit /b 1
)

echo Docker OK.
echo.

REM ==========================================================
REM 5. CHECK DOCKER ENGINE
REM ==========================================================
echo [5/7] Checking Docker Engine...
echo.

docker info >nul 2>nul

if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is installed but Docker Engine
    echo is not running.
    echo.
    echo Please start Docker Desktop and run setup again.
    echo.
    pause
    exit /b 1
)

echo Docker Engine OK.
echo.

REM ==========================================================
REM 6. START POSTGRESQL + REDIS
REM ==========================================================
echo [6/7] Starting PostgreSQL and Redis...
echo.

cd /d "%SERVER_DIR%"

docker compose up -d postgres redis

if errorlevel 1 (
    echo.
    echo ERROR: Failed to start PostgreSQL / Redis.
    echo.
    echo Docker logs:
    echo ------------------------------------------
    docker compose logs postgres redis
    echo ------------------------------------------
    echo.
    pause
    exit /b 1
)

echo.
echo PostgreSQL and Redis containers started.
echo.

REM ==========================================================
REM 7. WAIT


FOR POSTGRES + RUN ALEMBIC
REM ==========================================================
echo [7/7] Preparing database...
echo.

set "MAX_ATTEMPTS=30"
set "ATTEMPT=0"

:WAIT_POSTGRES

set /a ATTEMPT+=1

docker compose exec -T postgres pg_isready -U trainer -d trainer >nul 2>nul

if not errorlevel 1 (
    goto POSTGRES_READY
)

if !ATTEMPT! GEQ !MAX_ATTEMPTS! (
    echo.
    echo ERROR: PostgreSQL did not become ready.
    echo.
    echo PostgreSQL logs:
    echo ------------------------------------------
    docker compose logs postgres
    echo ------------------------------------------
    echo.
    pause
    exit /b 1
)

echo Waiting for PostgreSQL... !ATTEMPT!/!MAX_ATTEMPTS!

timeout /t 2 /nobreak >nul

goto WAIT_POSTGRES

:POSTGRES_READY

echo.
echo PostgreSQL is ready.
echo.

cd /d "%BACKEND_DIR%"

echo Running Alembic migrations...
echo.

"%VENV_DIR%\Scripts\python.exe" -m alembic upgrade head

if errorlevel 1 (
    echo.
    echo ERROR: Alembic migration failed.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo SETUP COMPLETED SUCCESSFULLY
echo ==========================================
echo.
echo Project:  %ROOT_DIR%
echo Python:   %VENV_DIR%
echo DB:       localhost:5433
echo Redis:    localhost:6379
echo ==========================================
echo.

pause

endlocal
exit /b 0