#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (macOS / Linux)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, avisa cómo instalarlo).
#    2. Descarga el bundle del wizard (que DEBE incluir resolver_pack/).
#    3. Crea un venv aislado (~/.venv) y, con --full, instala las
#       dependencias opcionales (torrents + resolvers de navegador).
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    curl -fsSL https://tu-servidor.com/install.sh | bash
#    curl -fsSL https://tu-servidor.com/install.sh | bash -s -- --full
#
#  Variables de entorno:
#    SYOPS_BUNDLE_URL   URL del zip del bundle (default al servidor de venta)
#    SYOPS_LINK_SERVER  URL /exec del Apps Script (si no la configurás acá,
#                       el wizard te avisa al descargar)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

BUNDLE_URL="${SYOPS_BUNDLE_URL:-https://tuservidor.com/syops-prep.zip}"
FULL=0
for arg in "$@"; do
  [ "$arg" = "--full" ] && FULL=1
done

# ── 1) Python ─────────────────────────────────────────────────────────
need_python() {
  echo "  ✗ No encontré Python 3 en PATH."
  echo "    macOS:  xcode-select --install   (o: brew install python)"
  echo "    Linux:  sudo apt install python3 python3-venv   (Debian/Ubuntu)"
  echo "            sudo pacman -S python python-venv        (Arch)"
  echo "  Volvé a correr este instalador cuando esté disponible." >&2
  exit 1
}

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
  PY="python"
else
  need_python
fi

# ── 2) Descargar el bundle ────────────────────────────────────────────
DEST="${HOME}/SyopS Prep"
TMP_ZIP="$(mktemp -d)/syops-prep.zip"

echo "  ↓ Bajo el wizard desde ${BUNDLE_URL} …"
curl -fsSL "${BUNDLE_URL}" -o "${TMP_ZIP}"
if [ ! -s "${TMP_ZIP}" ]; then
  echo "  ✗ La descarga quedó vacía. Revisá SYOPS_BUNDLE_URL." >&2
  exit 1
fi

rm -rf "${DEST}"
mkdir -p "${DEST}"
unzip -q "${TMP_ZIP}" -d "${DEST}"
rm -f "${TMP_ZIP}"

cd "${DEST}"

if [ ! -f syops_wizard.py ]; then
  echo "  ✗ El zip no trae syops_wizard.py en la raíz. Deszip ármalo bien." >&2
  exit 1
fi
if [ ! -d resolver_pack ]; then
  echo "  ⚠ El bundle NO incluye resolver_pack/: el wizard correrá pero no
       resolverá hosts (AkiraBox, Pixeldrain, …). Para venta incluí
       resolver_pack/ en el zip." >&2
fi

# ── 3) venv + dependencias ────────────────────────────────────────────
if [ ! -d .venv ]; then
  "${PY}" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ "${FULL}" -eq 1 ]; then
  echo "  ⧉ Instalando dependencias opcionales (torrents + navegador)…"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet libtorrent PySide6 cloudscraper
else
  echo "  ✔ Modo mínimo: sin dependencias extra (sirve para catálogo +
       descargas directas y Pixeldrain)."
  echo "    Para torrents/resolvers de navegador: rerun con --full"
fi

# ── 4) Ejecutar ───────────────────────────────────────────────────────
echo "  ▶ Abriendo SyopS Prep…"
exec python syops_wizard.py