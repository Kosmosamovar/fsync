@echo off
setlocal

REM Example usage:
REM run_sync.bat "C:\files\sync_folder" "D:\index\sync_index.json" "E:\kolo\fjfd\sync_folder" "F:\flash\copy_here"

if "%~4"=="" (
    echo Usage:
    echo   run_sync.bat "SOURCE_FOLDER" "INDEX_JSON" "DESTINATION_FOLDER"
    echo Example:
    echo   run_sync.bat "C:\files\sync_folder" "D:\index\sync_index.json" "E:\kolo\fjfd\sync_folder" "F:\flash\copy_here"
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
    echo Index file not found. Create it first:
    echo   sync_new_files.exe scan "%SOURCE%" --index "%INDEX%"
    exit /b 1
)

sync_new_files.exe copy "%SOURCE%" "%DEST%" --index "%INDEX%"
