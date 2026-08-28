@echo off
setlocal

if "%~3"=="" (
    echo Usage:
    echo   run_dry_run.bat "SOURCE_FOLDER" "INDEX_JSON" "DESTINATION_FOLDER"
    exit /b 1
)

set SOURCE=%~1
set INDEX=%~2
set DEST=%~3

if not exist "%SOURCE%" (
    echo Source folder not found: %SOURCE%
    exit /b 1
)

if not exist "%INDEX%" (
    echo Index file not found: %INDEX%
    exit /b 1
)

sync_new_files.exe copy "%SOURCE%" "%DEST%" --index "%INDEX%" --dry-run
