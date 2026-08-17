"""Auto-limpieza de Gatekeeper para SyopS Prep (macOS).

Al descargar el DMG y arrastrar Syops.app a Aplicaciones, macOS agrega el
atributo com.apple.quarantine. Al abrir, Gatekeeper muestra el popup de
"desarrollador no identificado". Este módulo resuelve eso automáticamente:

  - En el arranque normal: detecta la cuarentena en su propio bundle y, si
    existe, relanza la app con el flag --gatekeeper-cleanup. El proceso
    limpio ejecuta xattr -cr + codesign --ad-hoc sobre el bundle y vuelve
    a abrir la app (ahora sin cuarentena).
  - Con el flag --gatekeeper-cleanup: hace la limpieza (sin sudo, porque el
    usuario es dueño del bundle) y relanza la app normal.

Solo aplica en macOS y cuando se corre desde un bundle .app.
"""

import subprocess
import sys
from pathlib import Path


def _is_app_bundle() -> bool:
    return sys.platform == "darwin" and ".app" in str(Path(sys.argv[0]).resolve())


def _bundle_path() -> Path:
    """Devuelve la ruta del bundle .app (directorio que contiene Contents/)."""
    exe = Path(sys.argv[0]).resolve()
    # subir hasta encontrar el directorio que contiene Contents/
    for parent in exe.parents:
        if (parent / "Contents").exists():
            return parent
    return exe.parent


def _has_quarantine(bundle: Path) -> bool:
    try:
        result = subprocess.run(
            ["xattr", str(bundle)],
            capture_output=True, text=True, timeout=10,
        )
        return "com.apple.quarantine" in result.stdout
    except Exception:
        return False


def _cleanup_bundle(bundle: Path) -> bool:
    """Quita la cuarentena y re-firma ad-hoc. Devuelve True si todo ok."""
    try:
        # Quitar todos los atributos extendidos (incluye quarantine)
        subprocess.run(["xattr", "-cr", str(bundle)],
                       capture_output=True, text=True, timeout=60, check=True)
    except Exception:
        pass
    try:
        # Re-firmar ad-hoc (evita que Gatekeeper marque la app como corrupta)
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(bundle)],
            capture_output=True, text=True, timeout=120, check=True,
        )
    except Exception:
        pass
    return not _has_quarantine(bundle)


def _open_app(bundle: Path):
    subprocess.Popen(["open", str(bundle)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def handle_gatekeeper() -> bool:
    """Rutina de auto-limpieza de Gatekeeper. Devuelve True si la app debe
    continuar con el arranque normal, False si ya fue relanzada y hay que
    salir del proceso actual."""
    if not _is_app_bundle():
        return True
    bundle = _bundle_path()

    # Modo limpieza: ejecutado por la app tras relanzarse con el flag.
    if "--gatekeeper-cleanup" in sys.argv:
        _cleanup_bundle(bundle)
        _open_app(bundle)
        return False  # este proceso terminó su trabajo

    # Arranque normal con cuarentena detectada -> relanzar para limpiar.
    if _has_quarantine(bundle):
        try:
            args = ["open", str(bundle), "--args", "--gatekeeper-cleanup"]
            subprocess.Popen(args,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return False
        except Exception:
            # Si no se pudo relanzar, continuar de todas formas.
            return True

    return True
