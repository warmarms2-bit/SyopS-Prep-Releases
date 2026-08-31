# ═══════════════════════════════════════════════════════════════════
#  AKIRABOX RESOLVER (público) - Frontend para el worker de subprocess
#  Lanza un proceso hijo que usa QWebEngineView con su propio loop
#  nativo para resolver el link directo de AkiraBox.
#  Igual que resolver_pack, pero sin depender del pack: el worker vive en
#  services/akirabox_resolver_worker.py (requiere PySide6 en runtime).
# ═══════════════════════════════════════════════════════════════════

import logging
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)


AKIRABOX_HOSTS = ("akirabox.com", "akirabox.to")


def is_akirabox_url(url: str) -> bool:
    if not url:
        return False
    try:
        netloc = urllib.parse.urlparse(url).hostname
    except Exception:
        return False
    if not netloc:
        return False
    return any(netloc == h or netloc.endswith("." + h) for h in AKIRABOX_HOSTS)


def _find_python_executable() -> str:
    """Devuelve el ejecutable que puede correr el worker.
    En desarrollo es el Python del venv. En el bundle de PyInstaller
    es el mismo ejecutable de la app."""
    if getattr(sys, "frozen", False):
        return sys.executable
    python = shutil.which("python3") or shutil.which("python")
    if python:
        return python
    return sys.executable


def _worker_env(project_root: str) -> dict:
    env = dict(os.environ)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = project_root + os.pathsep + pythonpath
    return env


def resolve_akirabox_url(url: str, parent=None, timeout: int = 120, retries: int = 1) -> str:
    """
    Resuelve una URL de AkiraBox a un link directo de descarga.
    Lanza un proceso worker con su propio QApplication nativo.
    Retorna la URL directa o cadena vacía si falló / canceló.
    """
    if not is_akirabox_url(url):
        return url

    project_root = str(Path(__file__).resolve().parent.parent)
    exe = _find_python_executable()
    for attempt in range(retries + 1):
        # Si estamos en el bundle, el ejecutable es la app misma; de lo
        # contrario invocamos el worker como módulo con -m.
        if getattr(sys, "frozen", False):
            cmd = [exe, "--akirabox-worker", url, "--timeout", str(timeout)]
        else:
            cmd = [exe, "-m", "services.akirabox_resolver_worker",
                   "--akirabox-worker", url, "--timeout", str(timeout)]

        try:
            # Se descarta stderr del worker para evitar que los logs ruidosos
            # de Chromium llenen la pipe y bloqueen el proceso.
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=timeout + 15,
                cwd=project_root,
                env=_worker_env(project_root),
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("akirabox worker timed out (attempt %s)", attempt + 1)
            continue
        except Exception as e:
            logger.warning("akirabox subprocess error: %s", e)
            return ""

        if result.returncode != 0:
            logger.info("akirabox worker exit=%s", result.returncode)
            return ""

        for line in result.stdout.splitlines():
            if line.startswith("AKIRABOX_URL:"):
                return line[len("AKIRABOX_URL:"):].strip()
    return ""


def make_akirabox_resolver(link: str, app: str | None = None, **kwargs):
    """Factory de resolver_callback para AkiraBox (worker QWebEngine)."""

    def resolve() -> tuple[str, dict[str, str]]:
        result = resolve_akirabox_url(link, None, 120, 1)
        if not result:
            raise RuntimeError("AkiraBox no disponible")
        return result, {}

    return resolve