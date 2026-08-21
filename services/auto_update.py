"""Autoactualización del wizard (cliente terminal).

Al abrir, compara APP_VERSION con la versión publicada en el gist
(UPDATE_CHECK_URL). Si hay una versión más nueva, re-descarga el tarball del
repo público de GitHub y reemplaza el contenido de la instalación (carpeta de
la app), SIN tocar el estado/activación/descargas (SYOPS_DIR).

El proceso actual sigue corriendo (su bytecode ya está en memoria); el
reemplazo queda efectivo en el próximo arranque de `syops`.

Sin dependencias externas: usa urllib (stdlib) y `tar`/`unzip` del sistema,
igual que el instalador.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from app_config import APP_VERSION, UPDATE_CHECK_URL
from catalog.base import IS_MAC, IS_WIN

# URL del tarball/zip del repo público (fallback si el gist no trae download_url).
if IS_WIN:
    _BUNDLE_URL_FALLBACK = ("https://github.com/warmarms2-bit/SyopS-Prep-Releases/"
                            "archive/refs/heads/main.zip")
    _STRIP_CMD = False  # el zip trae la carpeta madre; la aplanamos
else:
    _BUNDLE_URL_FALLBACK = ("https://github.com/warmarms2-bit/SyopS-Prep-Releases/"
                            "archive/refs/heads/main.tar.gz")
    _STRIP_CMD = ["tar", "-xz", "--strip-components=1"]

# Clave del gist (por si cambia el formato). Default razonable.
_VERSION_KEYS = ("version", "latest", "latest_version")


def _parse_version(raw: str) -> tuple:
    """Convierte '1.2.3' en (1, 2, 3). No numérico → (0,)."""
    parts = []
    for seg in (raw or "").strip().split("."):
        try:
            parts.append(int("".join(c for c in seg if c.isdigit()) or 0))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def _fetch_gist_data(timeout: int = 8) -> dict | None:
    """Lee el gist de versiones. Devuelve el dict completo o None."""
    try:
        with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def fetch_latest_version(timeout: int = 8) -> str | None:
    """Lee la versión más reciente desde el gist. None si no puede conectar."""
    data = _fetch_gist_data(timeout)
    if not data:
        return None
    for key in _VERSION_KEYS:
        v = str(data.get(key, "")).strip()
        if v:
            return v
    return None


def _get_bundle_url(data: dict | None) -> str:
    """Devuelve la URL de descarga: del gist si la trae, si no el fallback."""
    if data:
        url = str(data.get("download_url", "")).strip()
        if url:
            return url
    return _BUNDLE_URL_FALLBACK


def check_for_update() -> tuple[bool, str | None, str | None]:
    """Devuelve (hay_update, nueva_version, version_actual).

    False si no hay update o no se pudo consultar.
    """
    latest = fetch_latest_version()
    if not latest:
        return False, None, APP_VERSION
    return (_parse_version(latest) > _parse_version(APP_VERSION),
            latest, APP_VERSION)


def _extract_zip_strip_first(zip_path: Path, dest: Path) -> None:
    """Windows: expande el zip y aplana la carpeta madre del repo."""
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    inner = None
    for p in dest.iterdir():
        if p.is_dir():
            inner = p
            break
    if inner is not None:
        for child in inner.iterdir():
            shutil.move(str(child), str(dest))
        shutil.rmtree(inner, ignore_errors=True)


def apply_update(timeout: int = 120) -> tuple[bool, str]:
    """Descarga y reemplaza la instalación con la versión del repo.

    Devuelve (ok, mensaje). No toca SYOPS_DIR (estado/descargas).
    """
    import tempfile as _tf
    # __file__ está en services/ → la raíz de la app es un nivel más arriba.
    dest = Path(__file__).resolve().parent.parent
    # Modo desarrollo: nunca autoactualizar un repo git (se rompería el árbol).
    if (dest / ".git").exists() or dest.name.endswith("Wizard"):
        return False, "Modo desarrollo: no se autoactualiza el repo."
    # Leer download_url del gist
    gist_data = _fetch_gist_data()
    bundle_url = _get_bundle_url(gist_data)
    tmp = Path(_tf.mkdtemp(prefix="syops-upd-"))
    try:
        archive = tmp / ("main.zip" if IS_WIN else "main.tar.gz")
        with urllib.request.urlopen(bundle_url, timeout=timeout) as resp:
            archive.write_bytes(resp.read())
        if not archive.stat().st_size:
            return False, "La descarga de la actualización quedó vacía."

        extract_dir = tmp / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            _extract_zip_strip_first(archive, extract_dir)
        else:
            subprocess.run(_STRIP_CMD + ["-C", str(extract_dir), "-f",
                                         str(archive)], check=True)

        if not (extract_dir / "syops_wizard.py").exists():
            return False, "La actualización no trae syops_wizard.py en la raíz."

        # Reemplazo: copiamos el contenido nuevo sobre la instalación actual.
        for src in extract_dir.iterdir():
            target = dest / src.name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(src), str(target))
        return True, "Actualización aplicada. Reiniciá `syops` para usarla."
    except Exception as exc:  # noqa: BLE001
        return False, f"No se pudo actualizar: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
