# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (Windows / PowerShell 5.1+)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, lo instala con winget).
#    2. Descarga el wizard directamente desde GitHub (repo público
#       SyopS-Prep-Releases) y lo deja en ~/"SyopS Prep".
#    3. Crea un venv aislado. El wizard es stdlib puro: no requiere
#       instalar dependencias extras.
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    irm https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.ps1 | iex
#
#  Variables:
#    -BundleUrl   URL del zip a descargar (default: GitHub main)
#    $env:SYOPS_LINK_SERVER → URL de descarga/catálogo (opcional)
# ═══════════════════════════════════════════════════════════════════════
param(
    [string]$BundleUrl = "https://github.com/warmarms2-bit/SyopS-Prep-Releases/archive/refs/heads/main.zip"
)
$ErrorActionPreference = "Stop"

# ── 1) Python ─────────────────────────────────────────────────────────
function Get-PythonCmd {
    foreach ($p in @("py", "python", "python3")) {
        try { & $p -c "import sys,sysconfig;print(sys.version_info[0],sys.version_info[1]);exit(0 if sys.version_info>=(3,8) else 1)" 2>$null | Out-Null; return $p } catch { }
    }
    $null
}
$PY = Get-PythonCmd
if (-not $PY) {
    Write-Host "  Instalando Python 3 con winget…" -ForegroundColor Yellow
    winget install --silent --accept-package-agreements --accept-source-agreements Python.Python.3
    $env:Path = "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python313;$($env:USERPROFILE)\AppData\Local\Programs\Python\Launcher;$env:Path"
    $PY = Get-PythonCmd
}
if (-not $PY) {
    Write-Host "✗ No pude instalar Python. Instalalo de python.org y volvé." -ForegroundColor Red
    exit 1
}

# ── 2) Descarga + descompresión ───────────────────────────────────────
$Profile = [System.Environment]::GetFolderPath("UserProfile")
if ([string]::IsNullOrWhiteSpace($Profile)) { $Profile = $env:USERPROFILE }
$DEST = [System.IO.Path]::Combine($Profile, "SyopS Prep")
$ZIP = [System.IO.Path]::Combine($env:TEMP, "syops-prep.zip")
$STAGE = [System.IO.Path]::Combine($env:TEMP, "syops-prep-stage")
Remove-Item $DEST -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Remove-Item $STAGE -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "  Bajo el wizard desde GitHub…" -ForegroundColor Cyan
Invoke-WebRequest -Uri $BundleUrl -OutFile $ZIP -UseBasicParsing
if ((Get-Item $ZIP).Length -eq 0) {
    Write-Host "✗ La descarga quedó vacía. Revisá -BundleUrl / SYOPS_BUNDLE_URL." -ForegroundColor Red
    exit 1
}

# Descomprimimos en TEMP (rutas absolutas, sin depender de la carpeta actual)
# y aplanamos la carpeta madre del zip de GitHub hacia el destino final.
Expand-Archive -Path $ZIP -DestinationPath $STAGE -Force
Remove-Item $ZIP -Force

New-Item -ItemType Directory -Force -Path $DEST | Out-Null
$wrapper = Get-ChildItem -Path $STAGE -Directory | Select-Object -First 1
if ($wrapper -and (Test-Path (Join-Path $wrapper.FullName "syops_wizard.py"))) {
    Get-ChildItem -Path $wrapper.FullName -Force | Move-Item -Destination $DEST -Force
    Remove-Item $wrapper.FullName -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Get-ChildItem -Path $STAGE -Force | Move-Item -Destination $DEST -Force
}
Remove-Item $STAGE -Recurse -Force -ErrorAction SilentlyContinue

Set-Location $DEST
if (-not (Test-Path "syops_wizard.py")) {
    Write-Host "✗ No se encontró syops_wizard.py en $DEST . Estructura:" -ForegroundColor Red
    Get-ChildItem $DEST | Select-Object Name | Format-Table
    exit 1
}

# ── 3) venv (stdlib puro, sin dependencias) ───────────────────────────
if (-not (Test-Path ".venv")) {
    & $PY -m venv .venv
}
Write-Host "  Listo: el wizard corre con el Python estándar (sin dependencias extra)." -ForegroundColor Green

# ── 3.5) Comando corto `syops` para reabrir sin reinstalar ────────────
$ShimDir = Join-Path $env:USERPROFILE "syops"
New-Item -ItemType Directory -Force -Path $ShimDir | Out-Null
$LaunchLine = "@echo off`r`n`"$DEST\.venv\Scripts\python.exe`" `"$DEST\syops_wizard.py`" %*"
Set-Content -Path (Join-Path $ShimDir "syops.cmd") -Value $LaunchLine -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$ShimDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$ShimDir", "User")
    Write-Host "  Comando syops creado. Reabrí la terminal (recarga el PATH) y usá:  syops" -ForegroundColor Green
} else {
    Write-Host "  Comando syops creado: reabrí el wizard cuando quieras con  syops" -ForegroundColor Green
}

# ── 4) Ejecutar (en la consola actual para que se vea el wizard) ──────
Write-Host "  Abriendo SyopS Prep…" -ForegroundColor Green
& ".venv\Scripts\python.exe" "syops_wizard.py"