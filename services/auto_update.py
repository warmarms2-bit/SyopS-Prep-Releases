"""Autoactualización del wizard."""

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

if IS_WIN:
    _BUNDLE_URL_FALLBACK = ("https://github.com/warmarms2-bit/SyopS-Prep-Releases/"
                            "archive/refs/heads/main.zip")
    _STRIP_CMD = False
else:
    _BUNDLE_URL_FALLBACK = ("https://github.com/warmarms2-bit/SyopS-Prep-Releases/"
                            "archive/refs/heads/main.tar.gz")
    _STRIP_CMD = ["tar", "-xz", "--strip-components=1"]

_VERSION_KEYS = ("version", "latest", "latest_version")

_PENDING_UPDATE_DIR = Path(__file__).resolve().parent.parent / ".pending_update"


def _parse_version(raw: str) -> tuple:
    parts = []
    for seg in (raw or "").strip().split("."):
        try:
            parts.append(int("".join(c for c in seg if c.isdigit()) or 0))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def _fetch_gist_data(timeout: int = 8) -> dict | None:
    import time
    sep = "&" if "?" in UPDATE_CHECK_URL else "?"
    url = f"{UPDATE_CHECK_URL}{sep}_t={int(time.time())}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def fetch_latest_version(timeout: int = 8) -> str | None:
    data = _fetch_gist_data(timeout)
    if not data:
        return None
    for key in _VERSION_KEYS:
        v = str(data.get(key, "")).strip()
        if v:
            return v
    return None


def _get_bundle_url(data: dict | None) -> str:
    if data:
        # El gist usa la clave "url"; el código histórico leía "download_url".
        # Aceptar ambas… pero SOLO si la extensión es la correcta para la
        # plataforma (zip en Windows, tar.gz en macOS/Linux): el gist apunta a
        # main.zip, y macOS/Linux deben extraer con tar (no con unzip).
        url = str(data.get("download_url") or data.get("url") or "").strip()
        if url:
            if IS_WIN and url.endswith(".zip"):
                return url
            if not IS_WIN and url.endswith(".tar.gz"):
                return url
    return _BUNDLE_URL_FALLBACK


def check_for_update() -> tuple[bool, str | None, str | None]:
    latest = fetch_latest_version()
    if not latest:
        return False, None, APP_VERSION
    return (_parse_version(latest) > _parse_version(APP_VERSION),
            latest, APP_VERSION)


def _extract_zip_strip_first(zip_path: Path, dest: Path) -> None:
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    # Strip GitHub wrapper dir (e.g. SyopS-Prep-Releases-main/)
    inner = None
    for p in dest.iterdir():
        if p.is_dir():
            inner = p
            break
    if inner is None:
        return
    # Also strip nested "SyopS Prep" dir if present
    nested = inner / "SyopS Prep"
    if nested.exists() and nested.is_dir():
        for child in nested.iterdir():
            target = inner / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            shutil.move(str(child), str(inner))
        shutil.rmtree(nested, ignore_errors=True)
    for child in inner.iterdir():
        target = dest / child.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        shutil.move(str(child), str(dest))
    shutil.rmtree(inner, ignore_errors=True)


def apply_pending_update() -> bool:
    """Aplica update descargado en un arranque anterior. True si aplicó."""
    pending = _PENDING_UPDATE_DIR
    marker = pending / "syops_wizard.py"
    if not marker.exists():
        return False
    # Verify the pending update is newer than current
    try:
        sys.path.insert(0, str(pending))
        from app_config import APP_VERSION as PENDING_VER
        sys.path.pop(0)
        if _parse_version(PENDING_VER) <= _parse_version(APP_VERSION):
            print(f"  ⊘ Update ignorado: {PENDING_VER} no es más reciente que {APP_VERSION}")
            shutil.rmtree(str(pending), ignore_errors=True)
            return False
    except Exception:
        pass
    print(f"  Aplicando actualización desde {pending}...")
    dest = Path(__file__).resolve().parent.parent
    skip_dirs = {dest.name.lower(), ".git", "__pycache__", ".venv", "resolver_pack"}
    for s in pending.iterdir():
        if s.is_dir() and s.name.lower() in skip_dirs:
            continue
        if s.is_file():
            shutil.copy2(str(s), str(dest / s.name))
        elif s.is_dir():
            target = dest / s.name
            if target.exists():
                shutil.rmtree(str(target), ignore_errors=True)
            shutil.copytree(str(s), str(target))
    for cache in dest.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    shutil.rmtree(str(pending), ignore_errors=True)
    print("  ✓ Archivos actualizados. Instalando dependencias...")
    _install_deps(dest)
    print("  ✓ Listo. Reiniciando...")
    return True


def _update_shim(dest: Path) -> None:
    """Actualiza el shim syops.cmd para que aplique .pending_update antes de lanzar Python."""
    shim_dir = Path.home() / "syops"
    shim = shim_dir / "syops.cmd"
    if not shim.exists():
        return
    shim_content = (
        "@echo off\r\n"
        f'if exist "{dest}\\.pending_update\\syops_wizard.py" (\r\n'
        f'  echo  Aplicando actualizacion...\r\n'
        f'  xcopy /E /Y /I "{dest}\\.pending_update\\*" "{dest}\\" >nul 2>&1\r\n'
        f'  for /d /r "{dest}" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul\r\n'
        f'  rmdir /s /q "{dest}\\.pending_update" 2>nul\r\n'
        f'  echo  Listo.\r\n'
        f')\r\n'
        f'"{dest}\\.venv\\Scripts\\python.exe" "{dest}\\syops_wizard.py" %*\r\n'
    )
    try:
        shim.write_text(shim_content, encoding="ascii")
    except Exception:
        pass


def _install_deps(dest: Path) -> None:
    """Instala dependencias en el venv después de una actualización."""
    if IS_WIN:
        pip = dest / ".venv" / "Scripts" / "pip.exe"
    else:
        pip = dest / ".venv" / "bin" / "pip"
    if not pip.exists():
        return
    try:
        subprocess.run(
            [str(pip), "install", "--quiet", "--upgrade", "pip"],
            capture_output=True, timeout=60,
        )
        subprocess.run(
            [str(pip), "install", "--quiet", "libtorrent", "PySide6", "cloudscraper"],
            capture_output=True, timeout=120,
        )
    except Exception:
        pass


def _sha256_of(path: Path) -> str:
    """SHA-256 en streaming de un archivo (sin cargarlo a memoria)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _verify_checksum(path: Path, expected_sha: str) -> str | None:
    """Verifica el sha256 de ``path`` contra ``expected_sha`` (hex).

    Devuelve un mensaje de error si no coincide, o ``None`` si está bien.
    Con ``expected_sha`` vacío devuelve ``None`` (sin verificación).
    """
    expected = (expected_sha or "").strip().lower()
    if not expected:
        return None
    if _sha256_of(path) != expected:
        return ("Checksum no coincide: el bundle descargado está corrupto "
                "o fue manipulado. No se aplica la actualización.")


def apply_update(timeout: int = 120) -> tuple[bool, str]:
    dest = Path(__file__).resolve().parent.parent
    if (dest / ".git").exists() or dest.name.endswith("Wizard"):
        return False, "Modo desarrollo: no se autoactualiza el repo."
    gist_data = _fetch_gist_data()
    bundle_url = _get_bundle_url(gist_data)
    expected_sha = str((gist_data or {}).get("sha256", "")).strip().lower()
    tmp = Path(tempfile.mkdtemp(prefix="syops-upd-"))
    try:
        archive = tmp / ("main.zip" if IS_WIN else "main.tar.gz")
        with urllib.request.urlopen(bundle_url, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 1024 * 1024
            downloaded = 0
            with open(archive, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  ▸ bajando pepa {pct}%   ", end="", flush=True)
                    else:
                        mb = downloaded / (1024 * 1024)
                        print(f"\r  ▸ bajando pepa {mb:.1f} MB   ", end="", flush=True)
            print()
        if not archive.stat().st_size:
            return False, "La descarga de la actualización quedó vacía."

        # Verificación de integridad: si el gist publica el sha256 del bundle,
        # lo exigimos. Si no lo publica, se aplica sin verificación (cadena de
        # suministro sin firma — el release pipeline debe empezar a publicarlo).
        checksum_err = _verify_checksum(archive, expected_sha)
        if checksum_err:
            return False, checksum_err

        extract_dir = tmp / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            _extract_zip_strip_first(archive, extract_dir)
        else:
            subprocess.run(_STRIP_CMD + ["-C", str(extract_dir), "-f",
                                         str(archive)], check=True)

        if not (extract_dir / "syops_wizard.py").exists():
            return False, "La actualización no trae syops_wizard.py en la raíz."

        # En Windows, no podemos sobreescribir .py en uso.
        # Guardamos en .pending_update; se aplica en el próximo arranque.
        if IS_WIN:
            if _PENDING_UPDATE_DIR.exists():
                shutil.rmtree(str(_PENDING_UPDATE_DIR), ignore_errors=True)
            shutil.copytree(str(extract_dir), str(_PENDING_UPDATE_DIR))
            _update_shim(dest)
            return True, "Actualización lista. Reiniciá `syops` para aplicarla."
        else:
            for src_dir, dirs, files in os.walk(str(extract_dir)):
                src_dir_p = Path(src_dir)
                rel = src_dir_p.relative_to(extract_dir)
                target_dir = dest / rel if str(rel) != "." else dest
                target_dir.mkdir(parents=True, exist_ok=True)
                for f in files:
                    shutil.copy2(str(src_dir_p / f), str(target_dir / f))
            for cache in dest.rglob("__pycache__"):
                shutil.rmtree(cache, ignore_errors=True)
            _install_deps(dest)
            return True, "Actualización aplicada. Reiniciá `syops` para usarla."
    except Exception as exc:
        return False, f"No se pudo actualizar: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
