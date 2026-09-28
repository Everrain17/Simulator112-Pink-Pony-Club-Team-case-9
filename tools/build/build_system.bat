@echo off
chcp 65001 >nul

cd /d "%~dp0"

call serv-112\.venv\Scripts\activate.bat

pyinstaller --clean --noconfirm --onefile --windowed --name "System112" system_launcher.py

pause