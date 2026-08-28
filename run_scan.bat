@echo off
setlocal

if "%~2"=="" (
    echo Usage:
    echo   run_scan.bat "SOURCE_FOLDER" "INDEX_JSON"
    exit /b 1
)

set SOURCE=%~1
set INDEX=%~2

if not exist "%SOURCE%" (
    echo Source folder not found: %SOURCE%
    exit /b 1
)

sync_new_files.exe scan "%SOURCE%" --index "%INDEX%"
