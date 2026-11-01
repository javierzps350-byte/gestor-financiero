@echo off
setlocal
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo Git for Windows no esta instalado.
    echo Instala Git una sola vez desde https://git-scm.com/download/win
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\configure_remote.ps1"
if errorlevel 1 pause
