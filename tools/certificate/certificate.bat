@echo off
chcp 65001 >nul
title System112 - Установка сертификата

echo ==========================================
echo      SYSTEM112: УСТАНОВКА СЕРТИФИКАТА
echo ==========================================
echo.

net session >nul 2>&1

if %errorlevel% neq 0 (
    echo [ОШИБКА] Необходимы права администратора.
    echo.
    echo Нажмите правой кнопкой по certificate.bat
    echo и выберите "Запуск от имени администратора".
    echo.
    pause
    exit /b 1
)

set "CERT=%~dp0ca.crt"

if not exist "%CERT%" (
    echo [ОШИБКА] Файл сертификата ca.crt не найден.
    echo.
    echo Ожидаемый путь:
    echo %CERT%
    echo.
    pause
    exit /b 1
)

echo [1/2] Сертификат найден:
echo %CERT%
echo.

echo [2/2] Установка сертификата в хранилище
echo Trusted Root Certification Authorities...
echo.

certutil -addstore -f "Root" "%CERT%"

if %errorlevel% neq 0 (
    echo.
    echo ==========================================
    echo [ОШИБКА] Не удалось установить сертификат.
    echo ==========================================
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo Сертификат успешно установлен!
echo ==========================================
echo.
echo Компьютер теперь доверяет сертификату
echo System112 Trainer Local CA.
echo.
echo Файл ca.crt и этот BAT-файл после этого
echo можно удалить с компьютера.
echo.
echo Повторная установка не требуется.
echo.

pause