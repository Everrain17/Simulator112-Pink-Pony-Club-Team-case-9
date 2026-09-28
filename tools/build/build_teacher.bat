@echo off
call serv-112\.venv\Scripts\activate.bat
pyinstaller --clean --noconfirm --onefile --windowed --name "System112_Teacher" --collect-all PySide6 launcher.py
pause