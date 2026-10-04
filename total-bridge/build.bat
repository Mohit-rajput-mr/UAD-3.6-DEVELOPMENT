@echo off
REM Build a single-file Windows executable.
pip install pyinstaller >/dev/null 2>&1
pyinstaller --onefile --name bridge --add-data "data;data" -p . bridge\cli.py
echo.
echo Built distridge.exe
