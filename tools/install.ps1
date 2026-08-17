# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (Windows / PowerShell 5.1+)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, lo instala con winget).
#    2. Descarga el bundle del wizard (que DEBE incluir resolver_pack/).
#    3. Crea un venv aislado y, con el switch -Full, instala las
#       dependencias opcionales (torrents + resolvers de navegador).
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    irm https://tu-servidor.com/install.ps1 | iex
#    irm https://tu-servidor.com/install.ps1 | iex -Args "-Full"
#
#  Variables:
#    -BundleUrl   URL del zip del bundle (default al servidor de venta)
#    -Full        instala libtorrent/PySide6/cloudscraper
#    $env:SYOPS_LINK_SERVER → URL /exec del Apps Script
# ═══════════════════════════════════════════════════════════════════════
param(
    [string]$BundleUrl = "https://tuservidor.com/syops-prep.zip",
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

Write-Host "  Bajo el wizard desde $BundleUrl …" -ForegroundColor Cyan
Invoke-WebRequest -Uri $BundleUrl -OutFile $ZIP -UseBasicParsing
if ((Get-Item $ZIP).Length -eq 0) {
    Write-Host "✗ La descarga quedó vacía. Revisá -BundleUrl / SYOPS_BUNDLE_URL." -ForegroundColor Red
    exit 1
}
Expand-Archive -Path $ZIP -DestinationPath $DEST -Force
Remove-Item $ZIP -Force

Set-Location $DEST
if (-not (Test-Path "syops_wizard.py")) {
    Write-Host "✗ El zip no trae syops_wizard.py en la raíz." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "resolver_pack")) {
    Write-Host "⚠ Ojo: el bundle no incluye resolver_pack/ — el wizard correrá pero no resolverá hosts." -ForegroundColor Yellow
}

# ── 3) venv + dependencias ────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    & $PY -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --upgrade --quiet pip
if ($Full) {
    Write-Host "  Instalando dependencias opcionales (torrents + navegador)…" -ForegroundColor Yellow
    & ".venv\Scripts\python.exe" -m pip install --quiet libtorrent PySide6 cloudscraper
} else {
    Write-Host "  Modo mínimo: sin dependencias extra (catálogo + descargas directas y Pixeldrain)."
    Write-Host "    Para torrents/navegador: rerun con  -Full"
}

# ── 4) Ejecutar (en la consola actual para que se vea el wizard) ──────
Write-Host "  Abriendo SyopS Prep…" -ForegroundColor Green
& ".venv\Scripts\python.exe" "syops_wizard.py"