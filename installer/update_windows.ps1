param([switch]$NoRestart)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path (Join-Path $ProjectRoot '.git'))) {
        throw 'No se encontro el historial Git. Esta actualizacion incremental requiere la instalacion preparada con Git.'
    }

    git --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Git no esta disponible.' }

    $remoteUrl = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteUrl)) {
        throw 'Todavia no hay un repositorio remoto configurado. Ejecuta configurar_actualizaciones.bat una sola vez.'
    }

    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo revisar el estado del codigo.' }
    if ($status) {
        Write-Host $status
        throw 'Hay cambios locales en el codigo. No se actualizo para evitar sobrescribirlos. Los datos de data/ no afectan esta comprobacion.'
    }

    $branch = git branch --show-current
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) { throw 'No se pudo identificar la rama.' }

    Write-Host 'Buscando cambios...' -ForegroundColor Cyan
    git fetch --prune origin
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron consultar las actualizaciones. Comprueba Internet y tus credenciales.' }

    $remoteRef = "origin/$branch"
    git show-ref --verify --quiet "refs/remotes/$remoteRef"
    if ($LASTEXITCODE -ne 0) { throw "No existe la rama remota $remoteRef. Revisa la configuracion del repositorio." }

    $behind = git rev-list --count "HEAD..$remoteRef"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo comparar la version instalada con el servidor.' }
    $ahead = git rev-list --count "$remoteRef..HEAD"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo verificar la sincronizacion.' }

    if ([int]$ahead -gt 0) {
        throw 'La copia local contiene commits que no estan en el servidor. No se hizo merge automatico; se necesita revisar la sincronizacion.'
    }

    if ([int]$behind -eq 0) {
        Write-Host 'Ya tienes la version mas reciente.' -ForegroundColor Green
        if (-not $NoRestart) {
            $open = Read-Host '¿Deseas abrir el programa? (S/N)'
            if ($open -match '^(s|si|sí)$') { Start-Process -FilePath (Join-Path $ProjectRoot 'run_windows.bat') }
        }
        exit 0
    }

    # Respalda datos de usuario antes de mover el codigo. No se suben a GitHub.
    $dataPath = Join-Path $ProjectRoot 'data'
    if (Test-Path $dataPath) {
        $backupRoot = Join-Path $env:LOCALAPPDATA 'GestorFinanciero\update_backups'
        New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $backupFile = Join-Path $backupRoot "datos_antes_actualizacion_$stamp.zip"
        $items = Get-ChildItem -LiteralPath $dataPath -Force
        if ($items.Count -gt 0) {
            Compress-Archive -Path (Join-Path $dataPath '*') -DestinationPath $backupFile -CompressionLevel Optimal
            Write-Host "Respaldo de datos creado: $backupFile" -ForegroundColor DarkGreen
        }
    }

    Write-Host "Hay $behind actualizacion(es). Aplicando solo los cambios nuevos..." -ForegroundColor Cyan
    git merge --ff-only $remoteRef
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo aplicar la actualizacion de forma segura.' }

    # Instala solo dependencias base declaradas por el proyecto; el nucleo puede seguir sin paquetes externos.
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (Test-Path $python) {
        & $python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt') --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { throw 'El codigo se actualizo, pero hubo un problema instalando dependencias. Revisa requirements.txt.' }
    }

    Write-Host ''
    Write-Host 'Actualizacion aplicada correctamente.' -ForegroundColor Green
    Write-Host 'La base de datos y las evidencias permanecen en data/.' -ForegroundColor Green

    if (-not $NoRestart) {
        Start-Process -FilePath (Join-Path $ProjectRoot 'run_windows.bat')
    }
}
finally {
    Pop-Location
}
