@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno local de Python...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo No se pudo crear el entorno. Verifica que Python 3.10 o posterior este instalado.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
