@echo off
chcp 65001 >nul
title Система-112: Запуск всей системы

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo ==========================================
echo      СИСТЕМА-112: ЗАПУСК
echo ==========================================
echo Корень: %ROOT%
echo.

:: =========================================================
:: 1. QWEN
:: =========================================================

echo [1/4] Запуск Qwen...

start "QWEN" /D "%ROOT%\llama-b8665-bin-win-cuda-13.1-x64" "%ComSpec%" /k ".\llama-server.exe -m .\qwen2.5-14b-instruct-q4_k_m.gguf -ngl 20 -c 4096 --port 8080 --host 0.0.0.0 --temp 0.55 --repeat-penalty 1.2 -t 6 --reasoning off"

:: =========================================================
:: 2. TTS SERVER
:: =========================================================

echo [2/4] Запуск TTS Server...

start "TTS SERVER" /D "%ROOT%\tts-server" "%ComSpec%" /k "call venv\Scripts\activate.bat & python tts_server.py"

:: =========================================================
:: 3. C# BACKEND
:: =========================================================

echo [3/4] Запуск C# Backend...

start "C# BACKEND" /D "%ROOT%" "%ComSpec%" /k "dotnet run"

:: =========================================================
:: 4. ADMIN TOOL
:: =========================================================

echo [4/4] Запуск Admin Tool...

if not exist "%ROOT%\serv-112\.venv\Scripts\activate.bat" (
echo [ОШИБКА] Venv Admin Tool не найден:
echo %ROOT%\serv-112.venv
pause
exit /b 1
)

start "ADMIN TOOL" /D "%ROOT%\serv-112" "%ComSpec%" /k "call .venv\Scripts\activate.bat & python -m admin_tool.main"

echo.
echo ==========================================
echo Все компоненты отправлены на запуск.
echo ==========================================
echo.
:: Файл-лаунчер можно закрыть.
exit /b 0
:: ---------------------------------------------------------
:: Qwen       → llama-server, порт 8080
:: TTS        → tts-server\venv\Scripts, tts_server.py
:: C#         → корень Simulator112, dotnet run
:: Admin Tool → serv-112.venv, admin_tool.main
:: Python     → Admin Tool сам запускает backend :8010
:: ---------------------------------------------------------
