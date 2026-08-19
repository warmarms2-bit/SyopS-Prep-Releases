#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  SyopS Prep — instalador ONE-LINER (macOS / Linux)
#
#  Qué hace:
#    1. Verifica Python 3.8+ (si falta, avisa cómo instalarlo).
#    2. Descarga el wizard directamente desde GitHub (repo público
#       SyopS-Prep-Releases) y lo deja en ~/"SyopS Prep".
#    3. Crea un venv aislado (~/"SyopS Prep"/.venv). El wizard es stdlib
#       puro: no requiere instalar dependencias extras.
#    4. Lanza el wizard en la terminal.
#
#  Uso:
#    curl -fsSL https://raw.githubusercontent.com/warmarms2-bit/SyopS-Prep-Releases/main/tools/install.sh | bash
#
#  Variables de entorno:
#    SYOPS_BUNDLE_URL   URL del tarball a descargar (default: GitHub main)
#    SYOPS_LINK_SERVER  URL de descarga/catálogo (opcional; si no está,
#                       el wizard corre en modo local sin descargas)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

BUNDLE_URL="${SYOPS_BUNDLE_URL:-https://github.com/warmarms2-bit/SyopS-Prep-Releases/archive/refs/heads/main.tar.gz}"

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

# ── 3) venv (stdlib puro, sin dependencias) ───────────────────────────
if [ ! -d .venv ]; then
  "${PY}" -m venv .venv
fi
echo "  ✔ Listo: el wizard corre con el Python estándar (sin dependencias extra)."

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
  *)
    ZSHRC="${HOME}/.zshrc"
    # El comando se agrega a la terminal: si no existe .zshrc se crea.
    if ! grep -q "${BIN_DIR}" "${ZSHRC}" 2>/dev/null; then
      printf '\nexport PATH="%s:$PATH"\n' "${BIN_DIR}" >> "${ZSHRC}"
    fi
    for rc in "${HOME}/.bashrc" "${HOME}/.profile"; do
      if [ -f "${rc}" ] && ! grep -q "${BIN_DIR}" "${rc}"; then
        printf '\nexport PATH="%s:$PATH"\n' "${BIN_DIR}" >> "${rc}"
      fi
    done
    ;;
esac
# Si hay un directorio ya en el PATH por defecto de macOS y escribible
# (/opt/homebrew/bin, /usr/local/bin), creamos los comandos también ahí:
# funcionan de inmediato, sin recargar la terminal ni abrir una nueva.
AUTO_BIN=""
for p in /opt/homebrew/bin /usr/local/bin; do
  if [ -d "$p" ] && [ -w "$p" ]; then
    ln -sf "${BIN_DIR}/syops" "$p/syops"
    ln -sf "${BIN_DIR}/eliminar-syops" "$p/eliminar-syops"
    AUTO_BIN="$p"
    break
  fi
done
echo "  ✔ Comando creado: reabrí el wizard cuando quieras con  syops"
if [ -n "${AUTO_BIN}" ]; then
  echo "  ✔ Listo para usar de una:  syops   (ya quedó en tu PATH actual)"
else
  echo "  ⚠ En la ventana actual ejecutá primero:   source ~/.zshrc"
  echo "    (o abrí una ventana nueva de Terminal; la vieja no lo habilita)"
fi

# ── 3.6) Comando `eliminar-syops` (desinstalar desde la terminal) ─────
cat > "${BIN_DIR}/eliminar-syops" <<EOF
#!/usr/bin/env bash
echo "Esto eliminará SyopS del equipo:"
echo "  • la app (${DEST})"
echo "  • el comando syops y este desinstalador"
echo "  • el estado, la activación y lo descargado (${HOME}/SYOPS)"
read -r -p "¿Continuar? (s/n) [n]: " ok
[ "\${ok:-n}" != "s" ] && [ "\${ok:-n}" != "S" ] && { echo "Cancelado."; exit 0; }
rm -rf "${DEST}"
rm -f "${BIN_DIR}/syops" "${BIN_DIR}/eliminar-syops"
rm -f /opt/homebrew/bin/syops /opt/homebrew/bin/eliminar-syops
rm -f /usr/local/bin/syops /usr/local/bin/eliminar-syops
rm -rf "${HOME}/SYOPS"
for rc in "\${HOME}/.zshrc" "\${HOME}/.bashrc" "\${HOME}/.profile"; do
  if [ -f "\$rc" ]; then
    tmp="\$(mktemp)"
    grep -v '.local/bin' "\$rc" > "\$tmp" && mv "\$tmp" "\$rc"
  fi
done
echo "✓ SyopS eliminado. Cerrá y reabrí la terminal."
EOF
chmod +x "${BIN_DIR}/eliminar-syops"
echo "  ✔ Comando creado: desinstalá con  eliminar-syops"

# ── 4) Ejecutar ───────────────────────────────────────────────────────
echo "  ▶ Abriendo SyopS Prep…"
exec .venv/bin/python syops_wizard.py