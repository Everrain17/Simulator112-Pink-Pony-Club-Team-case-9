@echo off
chcp 65001 >nul

echo ==========================================
echo      SYSTEM112: НАСТРОЙКА FIREWALL
echo ==========================================
echo.

net session >nul 2>&1

if %errorlevel% neq 0 (
echo [ОШИБКА] Запустите firewall.bat от имени администратора.
echo.
pause
exit /b 1
)

echo Открытие TCP порта 8010...
netsh advfirewall firewall add rule name="System112 Python 8010" dir=in action=allow protocol=TCP localport=8010

echo Открытие TCP порта 5000...
netsh advfirewall firewall add rule name="System112 CSharp 5000" dir=in action=allow protocol=TCP localport=5000

echo Открытие TCP порта 8000...
netsh advfirewall firewall add rule name="System112 TTS 8000" dir=in action=allow protocol=TCP localport=8000

echo.
echo ==========================================
echo Firewall настроен.
echo ==========================================
echo.

pause
