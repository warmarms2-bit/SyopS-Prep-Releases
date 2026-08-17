"""Servicio de detección, descarga e instalación de RustDesk.

No depende de Qt ni de widgets. La UI y el wizard pueden usar el mismo
servicio y decidir por separado cómo preguntar, mostrar progreso o manejar
un fallo.
"""

import asyncio
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app_config import RUSTDESK_URL, RUSTDESK_URL_MAC
from services.download_engine import DownloadEngine
from system.hardware import is_rustdesk_installed


@dataclass(frozen=True)
class RustDeskConfig:
    url: str
    filename: str


def config_for_platform(platform: str = None) -> RustDeskConfig:
    """Devuelve URL/nombre del instalador para macOS o Windows."""
    platform = platform or sys.platform
    if platform == "darwin":
        return RustDeskConfig(RUSTDESK_URL_MAC, "rustdesk.dmg")
    if platform == "win32":
        return RustDeskConfig(RUSTDESK_URL, "rustdesk.msi")
    raise RuntimeError(f"RustDesk no está soportado en {platform}")


def _mount_point_from_plist(raw: bytes) -> Path | None:
    """Extrae el punto de montaje del plist de hdiutil."""
    try:
        data = plistlib.loads(raw)
    except Exception:
        return None
    for image in data.get("system-entities", []):
        mount = image.get("mount-point")
        if mount:
            return Path(mount)
    return None


def _find_app(mount_point: Path) -> Path | None:
    candidate = mount_point / "RustDesk.app"
    if candidate.exists():
        return candidate
    return next(iter(mount_point.glob("*.app")), None)


def install_macos(dmg_path: Path, destination: Path = Path("/Applications/RustDesk.app")) -> bool:
    """Monta el DMG, copia RustDesk.app y desmonta siempre al terminar."""
    mount_point = None
    try:
        result = subprocess.run(
            ["hdiutil", "attach", str(dmg_path), "-nobrowse", "-quiet", "-plist"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return False
        mount_point = _mount_point_from_plist(result.stdout)
        if mount_point is None:
            return False
        for _ in range(15):
            if mount_point.exists():
                break
            import time
            time.sleep(1)
        app_path = _find_app(mount_point)
        if app_path is None:
            return False
        import shutil
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(app_path, destination)
        return destination.exists()
    finally:
        if mount_point is not None:
            subprocess.run(
                ["hdiutil", "detach", str(mount_point), "-quiet"],
                capture_output=True,
                timeout=10,
                check=False,
            )


def install_windows(msi_path: Path) -> bool:
    """Ejecuta msiexec y espera el resultado de instalación."""
    proc = subprocess.run(
        ["msiexec", "/i", str(msi_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


async def download_and_install(
    output_folder: Path,
    engine: DownloadEngine = None,
    progress_callback=None,
) -> tuple[bool, Path]:
    """Descarga e instala RustDesk para la plataforma actual.

    `progress_callback(name, pct, status, downloaded, total)` es opcional.
    Devuelve `(instalado, ruta_del_instalador)`.
    """
    config = config_for_platform()
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    installer = output_folder / config.filename
    engine = engine or DownloadEngine()

    completed = asyncio.get_running_loop().create_future()

    def on_progress(name, pct, status, downloaded, total):
        if progress_callback:
            progress_callback(name, pct, status, downloaded, total)

    def on_complete(name, success, size):
        if not completed.done():
            completed.set_result(bool(success))

    engine.progress.connect(on_progress)
    engine.completed.connect(on_complete)
    await engine.download_http(config.filename, config.url, output_folder)
    success = await completed if not completed.done() else completed.result()
    if not success or not installer.exists() or installer.stat().st_size < 1000:
        return False, installer

    if sys.platform == "darwin":
        return await asyncio.to_thread(install_macos, installer), installer
    if sys.platform == "win32":
        return await asyncio.to_thread(install_windows, installer), installer
    return False, installer


__all__ = [
    "RustDeskConfig", "config_for_platform", "is_rustdesk_installed",
    "install_macos", "install_windows", "download_and_install",
]
