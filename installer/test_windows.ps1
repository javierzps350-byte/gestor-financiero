$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project

py -3 -m compileall -q .
if ($LASTEXITCODE -ne 0) { throw "Falló la comprobación de sintaxis." }
py -3 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas." }
Write-Host "Pruebas completadas." -ForegroundColor Green
