$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path (Join-Path $ProjectRoot '.git'))) {
        throw 'Esta carpeta no contiene el historial Git del proyecto. Usa la carpeta instalada desde el paquete de actualización preparado.'
    }

    git --version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo ejecutar Git.' }

    Write-Host ''
    Write-Host 'Vincular Gestor Financiero con su repositorio privado' -ForegroundColor Cyan
    Write-Host 'Primero crea en GitHub un repositorio PRIVADO y VACIO.'
    Write-Host 'No agregues README, .gitignore ni licencia al crearlo.'
    Write-Host ''
    $remoteUrl = Read-Host 'Pega la URL HTTPS o SSH del repositorio'
    if ([string]::IsNullOrWhiteSpace($remoteUrl)) { throw 'No se proporciono una URL.' }
    if ($remoteUrl -notmatch '^(https://github\.com/[^/]+/[^/]+(?:\.git)?|git@github\.com:[^/]+/[^/]+(?:\.git)?)$') {
        throw 'La URL no parece ser un repositorio de GitHub HTTPS o SSH valido.'
    }

    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo revisar el estado del repositorio.' }
    if ($status) {
        throw 'Hay cambios locales sin guardar. No se conecto el remoto para evitar sobrescribir tu trabajo. Guarda o respalda esos cambios primero.'
    }

    $branch = git branch --show-current
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) { throw 'No se pudo identificar la rama actual.' }

    # Query the remote list first. Calling `git remote get-url origin` when
    # origin does not exist can emit a native-command error in PowerShell 7.
    $remoteNames = @(git remote)
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron consultar los remotos Git.' }

    if ($remoteNames -contains 'origin') {
        $existing = (git remote get-url origin 2>$null | Select-Object -First 1).Trim()
        if ($existing -eq $remoteUrl) {
            Write-Host 'El remoto origin ya apunta a esa direccion. Se conserva.' -ForegroundColor Green
        } else {
            Write-Host "Remoto actual: $existing"
            $replace = Read-Host '¿Deseas reemplazarlo? (S/N)'
            if ($replace -notmatch '^(s|si|sí)$') { throw 'Operacion cancelada; no se modifico el remoto.' }
            git remote set-url origin $remoteUrl
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo actualizar la URL del remoto.' }
        }
    } else {
        git remote add origin $remoteUrl
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el remoto.' }
    }

    # Preserve the current branch name (for example, `master`). The updater
    # follows the branch currently checked out and does not require `main`.

    Write-Host ''
    Write-Host 'Publicando el historial inicial en el repositorio privado...' -ForegroundColor Cyan
    Write-Host 'Git puede solicitar iniciar sesion en GitHub mediante el Administrador de credenciales.'
    git push -u origin $branch
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo publicar. Verifica que el repositorio remoto este vacio y que tu cuenta tenga permiso de escritura.'
    }

    Write-Host ''
    Write-Host 'Conexion configurada correctamente.' -ForegroundColor Green
    Write-Host 'A partir de ahora, usa actualizar.bat para recibir solo los cambios nuevos.' -ForegroundColor Green
}
finally {
    Pop-Location
}
