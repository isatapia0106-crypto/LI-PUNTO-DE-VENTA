$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo
$env:APP_ENV = 'demo'
$env:DATABASE_URL = 'sqlite:///./pos.db'

try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        } else {
            throw 'Instala Python 3.12 y activa la opción Add python.exe to PATH.'
        }
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
    }
    $python = Join-Path $repo '.venv\Scripts\python.exe'
    & $python -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias.' }

    $newDatabase = -not (Test-Path 'pos.db')
    if ($newDatabase) {
        & $python -c 'import backend.app.main'
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la base local.' }
        # A fresh demo has the current schema; stamp it for future Alembic upgrades.
        $env:APP_ENV = 'production'
        $env:JWT_SECRET = & $python -c 'import secrets; print(secrets.token_urlsafe(48))'
        & $python -m alembic stamp head
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo marcar la versión de la base.' }
        $env:APP_ENV = 'demo'
        Remove-Item Env:JWT_SECRET
    }

    $userCount = & $python scripts/check_local_db.py
    if ($LASTEXITCODE -ne 0) { throw 'Conserva pos.db y sigue docs/operations/SEGURIDAD_Y_MIGRACIONES.md antes de continuar.' }
    if ([int]$userCount -eq 0) {
        Write-Host 'Primera ejecución: crea un administrador. Empresa de demostración: 1.'
        & $python scripts/create_admin.py
        if ($LASTEXITCODE -ne 0) { throw 'No se creó el administrador.' }
    }

    $server = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $repo -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if ($server.HasExited) { throw 'El servidor se cerró. Revisa si el puerto 8000 está ocupado.' }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 1
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw 'La aplicación no respondió en el puerto 8000.' }
    Start-Process 'http://127.0.0.1:8000'
    Write-Host 'LI Punto de Venta abierto en http://127.0.0.1:8000'
    Write-Host "Servidor en proceso $($server.Id). Para detenerlo: Stop-Process -Id $($server.Id)"
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Presiona Enter para cerrar'
    exit 1
}
