@echo off
chcp 65001 >nul

echo ==========================================
echo      СИСТЕМА-112: ОСТАНОВКА
echo ==========================================
echo.

echo Остановка Python...
taskkill /F /IM python.exe >nul 2>&1

echo Остановка Qwen...
taskkill /F /IM llama-server.exe >nul 2>&1

echo Остановка C# Backend...
taskkill /F /IM dotnet.exe >nul 2>&1

echo.
echo ==========================================
echo Все процессы остановлены.
echo ==========================================
pause