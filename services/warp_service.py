"""WARP (Cloudflare 1.1.1.1) — oculta la IP real del cliente al bajar torrents.

Se invoca SOLO cuando la selección del wizard incluye descargas por torrent
directo (libtorrent) y TorBox NO está activo. Con WARP conectado, todo el
tráfico sale por el túnel WireGuard de Cloudflare: los peers ven la IP de
Cloudflare y el ISP ve WireGuard cifrado (no detecta torrents).

Notas honestas (ver docs):
- Cloudflare desaconseja P2P pesado por WARP (puede haber throttling).
- No es anonimato real frente a Cloudflare; sí oculta la IP real a los peers.
- Requiere admin para instalar (sudo/msiexec) y una cuenta WARP gratuita.

Desactivable con ``SYOPS_NO_WARP=1`` (para el técnico o tests).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from app_config import WARP_URL_MAC, WARP_URL_WIN


def needs_torrent(tasks) -> bool:
    """True si alguna tarea del plan se baja por torrent directo (libtorrent).

    Las tareas ``torbox`` (debrid) NO cuentan: ahí el cliente no entra al swarm.
    """
    return any(getattr(t, "method", None) == "torrent" for t in (tasks or []))


def warp_cli_path() -> str | None:
    """Ruta del binario warp-cli (o None si WARP no está instalado)."""
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates = [Path(pf) / "Cloudflare" / "Cloudflare WARP" / "warp-cli.exe"]
    else:
        candidates = [
            Path("/Applications/Cloudflare WARP.app/Contents/Resources/warp-cli"),
            Path("/usr/local/bin/warp-cli"),
            Path("/opt/homebrew/bin/warp-cli"),
        ]
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except OSError:
            continue
    return shutil.which("warp-cli")


def _run(cli: str, args, timeout: int = 90) -> tuple[int, str]:
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as exc:
        return -1, str(exc)


def warp_connected(cli: str) -> bool:
    """True si WARP está conectado (status contiene 'Connected')."""
    rc, out = _run(cli, ["status"], timeout=30)
    return rc == 0 and "connected" in out.lower()


def warp_install() -> tuple[bool, str]:
    """Descarga e instala el instalador oficial de WARP (requiere admin)."""
    url = WARP_URL_WIN if sys.platform == "win32" else WARP_URL_MAC
    tmp = Path(tempfile.mkdtemp(prefix="syops-warp-"))
    installer = tmp / ("warp.msi" if sys.platform == "win32" else "warp.pkg")
    try:
        print(f"  → Descargando WARP: {url}")
        urllib.request.urlretrieve(url, installer)
        if not installer.stat().st_size:
            return False, "descarga de WARP vacía"
        if sys.platform == "win32":
            r = subprocess.run(
                ["msiexec", "/i", str(installer), "/qn", "/norestart"],
                capture_output=True, timeout=600)
            return r.returncode == 0, "msiexec instaló WARP"
        # macOS: si el wizard ya corre como root (elevación al inicio) no
        # hace falta sudo; si no, sudo pedirá la clave en la terminal.
        cmd = ["installer", "-pkg", str(installer), "-target", "/"]
        if os.geteuid() != 0:
            cmd = ["sudo", *cmd]
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        return r.returncode == 0, "installer instaló WARP"
    except Exception as exc:
        return False, f"error instalando WARP: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_warp() -> tuple[bool, str]:
    """Asegura WARP instalado y conectado. Devuelve (ok, mensaje)."""
    if os.environ.get("SYOPS_NO_WARP", "") in ("1", "true", "True"):
        return False, "WARP desactivado por SYOPS_NO_WARP=1"

    cli = warp_cli_path()
    if cli is None:
        print("  → WARP no está instalado; instalando…")
        ok, msg = warp_install()
        if not ok:
            return False, f"no se pudo instalar WARP: {msg}"
        cli = warp_cli_path()
        if cli is None:
            return False, "WARP instalado pero no se encontró warp-cli"

    if warp_connected(cli):
        return True, "WARP ya conectado (IP oculta para torrents)"

    # Primera vez: registrar el equipo (cuenta WARP gratuita) y conectar.
    rc, out = _run(cli, ["register"])
    if rc != 0 and "already" not in out.lower():
        # Algunas versiones requieren aceptar los términos primero.
        _run(cli, ["accept-tos"])
        rc, out = _run(cli, ["register"])
    rc2, out2 = _run(cli, ["connect"])
    if warp_connected(cli):
        return True, "WARP conectado (IP oculta para torrents)"
    return False, f"no se pudo conectar WARP: {out2 or out or 'error desconocido'}"
