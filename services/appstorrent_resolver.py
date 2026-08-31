# ═══════════════════════════════════════════════════════════════════
#  APPSTORENT RESOLVER (público) - Frontend para el worker de subprocess
#  Resuelve links de appstorrent.ru a un link directo de descarga.
#
#  Estrategia en dos pasos (mismo patrón que akirabox_resolver.py):
#    1. cloudscraper (si está instalado): intenta resolver el challenge de
#       Cloudflare (IUAM) y obtener la URL directa sin abrir ventana.
#    2. worker QWebEngine: si el challenge es Turnstile (interactivo),
#       muestra la ventana para que el usuario lo resuelva manualmente y
#       captura la descarga real.
#
#  appstorrent usa DataLife Engine: la descarga real es un redirect desde
#  /index.php?do=download&id=<id> a /engine/download.php?id=<id> o a un
#  archivo en /uploads/.
# ═══════════════════════════════════════════════════════════════════

import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

APPSTORENT_HOST = "appstorrent.ru"


def is_appstorrent_url(url: str) -> bool:
    if not url:
        return False
    try:
        netloc = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    return netloc == APPSTORENT_HOST or netloc.endswith("." + APPSTORENT_HOST)


def _find_python_executable() -> str:
    """Devuelve el ejecutable que puede correr el worker.
    En desarrollo es el Python del venv. En el bundle es el ejecutable."""
    if getattr(sys, "frozen", False):
        return sys.executable
    python = shutil.which("python3") or shutil.which("python")
    if python:
        return python
    return sys.executable


def _resolve_with_cloudscraper(url: str, timeout: int = 40) -> str:
    """Intenta resolver el challenge con cloudscraper (IUAM, sin ventana)."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            ct = (r.headers.get("content-type", "") or "").lower()
            if "html" not in ct and "text" not in ct:
                return r.url
            for m in re.finditer(
                r'href=["\']([^"\']+(?:\.pkg|\.dmg|\.zip|\.rar|\.7z)[^"\']*)["\']',
                r.text,
            ):
                return urllib.parse.urljoin(r.url, m.group(1))
    except Exception as e:
        logger.info("cloudscraper falló: %s", e)
    return ""


def resolve_appstorrent_url(url: str, parent=None, timeout: int = 180, retries: int = 1,
                            dest_dir=None) -> str:
    """
    Resuelve una URL de appstorrent a un link directo de descarga.

    1. Intenta cloudscraper (sin ventana).
    2. Si falla (Turnstile), lanza el worker QWebEngine visible para que el
       usuario resuelva el captcha y se captura la descarga real.
    Retorna la URL directa o cadena vacía si falla.
    """
    if not is_appstorrent_url(url):
        return url

    # Paso 1: cloudscraper (rápido, sin ventana).
    result = _resolve_with_cloudscraper(url, 40)
    if result:
        return result

    # Paso 2: worker QWebEngine visible (como AkiraBox).
    project_root = str(Path(__file__).resolve().parent.parent)
    exe = _find_python_executable()
    env = dict(os.environ)
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    for attempt in range(retries + 1):
        if getattr(sys, "frozen", False):
            cmd = [exe, "--appstorrent-worker", url, "--timeout", str(timeout)]
        else:
            cmd = [exe, "-m", "services.appstorrent_resolver_worker",
                   "--appstorrent-worker", url, "--timeout", str(timeout)]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=timeout + 20,
                cwd=project_root,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            continue
        except Exception as e:
            logger.warning("appstorrent subprocess error: %s", e)
            return ""

        if result.returncode != 0:
            continue

        for line in result.stdout.splitlines():
            if line.startswith("APPSTORENT_URL:"):
                return line[len("APPSTORENT_URL:"):].strip()
    return ""


def make_appstorrent_resolver(link: str, dest_dir=None, **kwargs):
    """Factory de resolver_callback para Appstorrent (cloudscraper + fallback navegador)."""

    def resolve() -> tuple[str, dict[str, str]]:
        result = resolve_appstorrent_url(link, None, 180, 1, dest_dir=dest_dir)
        if not result:
            # Turnstile no resoluble: se abrió el navegador del usuario para
            # descarga manual. No es un error fatal: el usuario descarga aparte.
            raise RuntimeError("Appstorrent requiere descarga manual (Cloudflare Turnstile)")
        return result, {}

    return resolve