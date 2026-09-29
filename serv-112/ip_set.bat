@echo off
setlocal

echo ==========================================
echo System112 - Updating SERVER_HOST
echo ==========================================
echo.

set "CONFIG=%~dp0admin_tool\config.py"
set "CURRENT_IP="

if not exist "%CONFIG%" (
    echo ERROR: config.py not found:
    echo %CONFIG%
    pause
    exit /b 1
)

echo Detecting current IPv4...

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /R /C:"IPv4"') do (
    for /f "tokens=* delims= " %%B in ("%%A") do (
        if not defined CURRENT_IP (
            echo %%B | findstr /R /B /C:"192\.168\." >nul
            if not errorlevel 1 set "CURRENT_IP=%%B"
        )
    )
)

if not defined CURRENT_IP (
    echo ERROR: Could not find 192.168.x.x IPv4 address.
    echo.
    echo Current network configuration:
    ipconfig
    echo.
    pause
    exit /b 1
)

echo Detected IP: %CURRENT_IP%
echo.

powershell -NoProfile -Command ^
    "$p='%CONFIG%';" ^
    "$ip='%CURRENT_IP%';" ^
    "$c=[IO.File]::ReadAllText($p);" ^
    "$line='SERVER_HOST: str = _get(\"SERVER_HOST\", \"'+$ip+'\") or \"'+$ip+'\"';" ^
    "$c=[regex]::Replace($c,'(?m)^SERVER_HOST\s*:\s*str\s*=.*$',[System.Text.RegularExpressions.MatchEvaluator]{param($m) $line});" ^
    "[IO.File]::WriteAllText($p,$c,(New-Object System.Text.UTF8Encoding($false)))"

if errorlevel 1 (
    echo ERROR: Failed to update config.py
    pause
    exit /b 1
)

echo.
echo ==========================================
echo DONE
echo ==========================================
echo.
echo SERVER_HOST = %CURRENT_IP%
echo.

pause