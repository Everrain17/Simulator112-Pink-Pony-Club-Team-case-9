@echo off
chcp 65001 >nul
title System112 - Загрузка Qwen

cd /d "%~dp0"

set "ROOT=%~dp0..\..\"
set "QWEN_DIR=%ROOT%llama-b8665-bin-win-cuda-13.1-x64"
set "MODEL=%QWEN_DIR%\qwen2.5-14b-instruct-q4_k_m.gguf"

set "MODEL_URL=https://huggingface.co/TheRains/Qwen2.5-14B-Instruct-Q4_K_M-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf?download=true"

echo ==========================================
echo       SYSTEM112: ЗАГРУЗКА QWEN
echo ==========================================
echo.

if exist "%MODEL%" (
    echo [OK] Модель уже существует:
    echo %MODEL%
    echo.
    echo Повторная загрузка не требуется.
    echo.
    pause
    exit /b 0
)

if not exist "%QWEN_DIR%" (
    echo [ОШИБКА] Папка llama.cpp не найдена:
    echo %QWEN_DIR%
    echo.
    echo Убедитесь, что папка llama-b8665-bin-win-cuda-13.1-x64
    echo находится в корне Simulator112.
    echo.
    pause
    exit /b 1
)

where curl >nul 2>&1

if %errorlevel% neq 0 (
    echo [ОШИБКА] В системе не найден curl.
    echo.
    echo В Windows 10/11 curl обычно уже установлен.
    echo.
    pause
    exit /b 1
)

echo Модель:
echo qwen2.5-14b-instruct-q4_k_m.gguf
echo.
echo Размер: примерно 9 GB
echo.
echo Источник:
echo Hugging Face / TheRains
echo.
echo Начинается загрузка...
echo.

curl.exe -L ^
    --fail ^
    --retry 10 ^
    --retry-delay 5 ^
    --retry-all-errors ^
    -C - ^
    -o "%MODEL%" ^
    "%MODEL_URL%"

if %errorlevel% neq 0 (
    echo.
    echo ==========================================
    echo [ОШИБКА] Загрузка не завершена.
    echo ==========================================
    echo.
    echo Если загрузка была прервана, запустите
    echo этот BAT повторно.
    echo.
    echo Файл будет продолжен с места остановки.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo       QWEN УСПЕШНО ЗАГРУЖЕН
echo ==========================================
echo.
echo Файл:
echo %MODEL%
echo.
echo Теперь модель готова для запуска System112.
echo.

pause
exit /b 0