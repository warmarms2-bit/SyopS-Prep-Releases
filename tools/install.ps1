# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (Windows / PowerShell 5.1+)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, lo instala con winget).
#    2. Descarga el wizard directamente desde GitHub (repo público
#       SyopS-Prep-Releases) y lo deja en ~/"SyopS Prep".
#    3. Crea un venv aislado y, con el switch -Full, instala las
#       dependencias opcionales (torrents).
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    irm https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.ps1 | iex
#    irm https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.ps1 | iex -Args "-Full"
#
#  Variables:
#    -BundleUrl   URL del zip a descargar (default: GitHub main)
#    -Full        instala libtorrent
#    $env:SYOPS_LINK_SERVER → URL de descarga/catálogo (opcional)
# ═══════════════════════════════════════════════════════════════════════
param(
    [string]$BundleUrl = "https://github.com/warmarms2-bit/SyopS-Prep-Releases/archive/refs/heads/main.zip",
    [switch]$Full
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
$DEST = Join-Path $HOME "SyopS Prep"
$ZIP = Join-Path $env:TEMP "syops-prep.zip"
Remove-Item $DEST -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

Write-Host "  Bajo el wizard desde GitHub…" -ForegroundColor Cyan
Invoke-WebRequest -Uri $BundleUrl -OutFile $ZIP -UseBasicParsing
if ((Get-Item $ZIP).Length -eq 0) {
    Write-Host "✗ La descarga quedó vacía. Revisá -BundleUrl / SYOPS_BUNDLE_URL." -ForegroundColor Red
    exit 1
}
Expand-Archive -Path $ZIP -DestinationPath $DEST -Force
Remove-Item $ZIP -Force

# GitHub empaqueta el repo en una carpeta madre: la aplanamos.
$Inner = Get-ChildItem -Path $DEST -Directory | Select-Object -First 1
if ($Inner) {
    Get-ChildItem -Path $Inner.FullName | Move-Item -Destination $DEST -Force
    Remove-Item $Inner -Force
}

Set-Location $DEST
if (-not (Test-Path "syops_wizard.py")) {
    Write-Host "✗ El paquete no trae syops_wizard.py en la raíz." -ForegroundColor Red
    exit 1
}

# ── 3) venv + dependencias ────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    & $PY -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --upgrade --quiet pip
if ($Full) {
    Write-Host "  Intentando instalar libtorrent (torrents)…" -ForegroundColor Yellow
    & ".venv\Scripts\python.exe" -m pip install --quiet libtorrent
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  libtorrent listo (torrents disponibles)." -ForegroundColor Green
    } else {
        Write-Host "  Ojo: libtorrent no tiene binario para este Python — torrents desactivados." -ForegroundColor Yellow
        Write-Host "  El resto del wizard funciona igual (catálogo + descargas directas)."
    }
} else {
    Write-Host "  Modo mínimo: solo el estándar de Python (catálogo + descargas directas)."
    Write-Host "    Para torrents: rerun con  -Full"
}

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