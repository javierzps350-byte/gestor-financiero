$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project

Write-Host "Preparando entorno de compilacion..." -ForegroundColor Cyan
py -3 -m venv .build-venv
& .\.build-venv\Scripts\python.exe -m pip install --upgrade pip
& .\.build-venv\Scripts\python.exe -m pip install pyinstaller

Write-Host "Generando aplicacion portable para Windows..." -ForegroundColor Cyan
& .\.build-venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir `
    --name GestorFinanciero `
    --add-data "src\database\schema.sql;src\database" `
    main.py

Write-Host "Compilacion terminada." -ForegroundColor Green
Write-Host "Ejecutable: $Project\dist\GestorFinanciero\GestorFinanciero.exe"
Write-Host "Los datos del usuario se guardaran en %LOCALAPPDATA%\GestorFinanciero"
