@echo off
setlocal

set APP_VERSION=1.0.1
set PYTHON_CMD="C:\dev\video_spy\venv\Scripts\python.exe"
set OUT_NAME=fsync.exe

if not exist %PYTHON_CMD% (
    echo Python interpreter not found: %PYTHON_CMD%
    echo Update the path in this file if needed.
    exit /b 1
)

%PYTHON_CMD% -m PyInstaller --onefile --distpath .\dist --name fsync sync_new_files.py

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo Build finished. Output: .\dist\%OUT_NAME%
