#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (macOS / Linux)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, avisa cómo instalarlo).
#    2. Descarga el wizard directamente desde GitHub (repo público
#       SyopS-Prep-Releases) y lo deja en ~/"SyopS Prep".
#    3. Crea un venv aislado (~/"SyopS Prep"/.venv) y, con --full, instala
#       las dependencias opcionales (torrents).
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    curl -fsSL https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.sh | bash
#    curl -fsSL https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.sh | bash -s -- --full
#
#  Variables de entorno:
#    SYOPS_BUNDLE_URL   URL del tarball a descargar (default: GitHub main)
#    SYOPS_LINK_SERVER  URL de descarga/catálogo (opcional; si no está,
#                       el wizard corre en modo local sin descargas)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

BUNDLE_URL="${SYOPS_BUNDLE_URL:-https://github.com/warmarms2-bit/SyopS-Prep-Releases/archive/refs/heads/main.tar.gz}"
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

# ── 2) Descargar el wizard desde GitHub ───────────────────────────────
DEST="${HOME}/SyopS Prep"
TMP_TGZ="$(mktemp -d)/syops-prep.tar.gz"

echo "  ↓ Bajo el wizard desde GitHub …"
curl -fsSL "${BUNDLE_URL}" -o "${TMP_TGZ}"
if [ ! -s "${TMP_TGZ}" ]; then
  echo "  ✗ La descarga quedó vacía. Revisá SYOPS_BUNDLE_URL." >&2
  exit 1
fi

rm -rf "${DEST}"
mkdir -p "${DEST}"
# GitHub empaqueta el repo en una carpeta madre: la quitamos con strip.
tar -xz --strip-components=1 -C "${DEST}" -f "${TMP_TGZ}"
rm -f "${TMP_TGZ}"

cd "${DEST}"

if [ ! -f syops_wizard.py ]; then
  echo "  ✗ El paquete no trae syops_wizard.py en la raíz." >&2
  exit 1
fi

# ── 3) venv + dependencias ────────────────────────────────────────────
if [ ! -d .venv ]; then
  "${PY}" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ "${FULL}" -eq 1 ]; then
  echo "  ⧉ Intentando instalar libtorrent (torrents)…"
  if python -m pip install --quiet libtorrent; then
    echo "  ✔ libtorrent listo (torrents disponibles)."
  else
    echo "  ⚠ libtorrent no tiene binario para este Python; torrents desactivados."
    echo "    El resto del wizard funciona igual (catálogo + descargas directas)."
  fi
else
  echo "  ✔ Modo mínimo: solo el estándar de Python (catálogo + descargas directas)."
  echo "    Para torrents: rerun con --full"
fi

# ── 3.5) Comando corto `syops` para reabrir sin reinstalar ────────────
BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"
cat > "${BIN_DIR}/syops" <<EOF
#!/usr/bin/env bash
exec "${DEST}/.venv/bin/python" "${DEST}/syops_wizard.py" "\$@"
EOF
chmod +x "${BIN_DIR}/syops"
case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) for rc in "${HOME}/.zshrc" "${HOME}/.bashrc" "${HOME}/.profile"; do
       if [ -f "${rc}" ] && ! grep -q "${BIN_DIR}" "${rc}"; then
         printf '\nexport PATH="%s:$PATH"\n' "${BIN_DIR}" >> "${rc}"
       fi
     done ;;
esac
echo "  ✔ Comando creado: reabrí el wizard cuando quieras con  syops"

# ── 4) Ejecutar ───────────────────────────────────────────────────────
echo "  ▶ Abriendo SyopS Prep…"
exec python syops_wizard.py