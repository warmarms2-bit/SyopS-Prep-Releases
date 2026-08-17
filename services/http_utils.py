#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  HTTP UTILS - Helpers genéricos compartidos para descargas
#  (progreso, hashes, nombres de archivo, descarga segmentada).
#  No contiene know-how de hosts: las utilidades privadas de resolución
#  viven en resolver_pack/ (no rastreado en el repo público).
# ═══════════════════════════════════════════════════════════════════

import math
import os
import re
import time
import hashlib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# ── UTILIDADES DE PROGRESO ────────────────────────────────────────
def _safe_eta(seconds_float: float) -> int:
    """Convierte segundos estimados a int sin OverflowError por infinito."""
    if not math.isfinite(seconds_float):
        return 0
    # Limite razonable: ~20 años (evita numeros absurdos y desbordes)
    return int(min(max(seconds_float, 0), 630_720_000))


def _safe_pct(value) -> int:
    """Convierte un valor de progreso a int entre 0 y 100 sin OverflowError."""
    try:
        v = float(value)
    except Exception:
        return 0
    if not math.isfinite(v):
        return 0
    return int(max(0, min(v, 100)))


def _format_eta(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    elif seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


# ── HASHES Y VERIFICACIÓN ────────────────────────────────────────
def _verify_file_sha256(path: Path, expected_hash: str) -> bool:
    """Verifica que el hash SHA256 del archivo coincida con el esperado."""
    if not expected_hash or not path.exists():
        return True
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        actual = h.hexdigest().lower()
        expected = expected_hash.lower().strip()
        if actual != expected:
            logger.error("SHA256 mismatch: %s vs %s", actual, expected)
            return False
        return True
    except Exception as e:
        logger.warning("error verifying hash: %s", e)
    return False


def validate_downloaded_file(path: Path, expected_size: int = 0) -> bool:
    """Valida que el archivo descargado no sea HTML y tenga el tamaño esperado."""
    if not path.exists():
        return False
    actual_size = path.stat().st_size
    if expected_size > 0 and actual_size != expected_size:
        logger.warning("size mismatch: %s vs %s", actual_size, expected_size)
        return False
    if actual_size < 8192:
        # Archivos muy pequeños pueden ser HTML de error.
        try:
            with open(path, "rb") as f:
                header = f.read(2048)
            if header.startswith(b"<!DOCTYPE") or header.startswith(b"<html") or b"<!DOCTYPE" in header[:512]:
                logger.warning("downloaded file is HTML")
                return False
        except Exception:
            pass
    return True


# ── NOMBRES Y EXTENSIONES ─────────────────────────────────────────
def _filename_from_content_disposition(header: str) -> str:
    """Extrae el nombre de archivo del header Content-Disposition."""
    if not header:
        return ""
    try:
        # Busca filename="..." o filename*=UTF-8''...
        m = re.search(r'filename\*?=\s*"?([^";]+)"?', header)
        if m:
            name = m.group(1).strip()
            if name.startswith("UTF-8'"):
                name = name.split("'", 2)[-1]
            if name.startswith("utf-8'"):
                name = name.split("'", 2)[-1]
            return urllib.parse.unquote(name)
    except Exception:
        pass
    return ""


def _guess_extension_from_url(url: str) -> str:
    """Devuelve la extensión de archivo inferida desde una URL de descarga.
    Si no se puede determinar, usa .zip por defecto."""
    KNOWN_EXTS = {".pkg", ".dmg", ".exe", ".msi", ".zip", ".7z", ".tar", ".gz", ".bz2", ".rar"}
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if not path:
            return ".zip"
        # Quer query params de path (aunque path no debería tenerlos)
        lower = path.lower()
        for ext in KNOWN_EXTS:
            if lower.endswith(ext):
                return ext
        # Intentar extraer la extensión final del path
        ext = os.path.splitext(path)[1]
        if ext:
            return ext
    except Exception:
        pass
    return ".zip"


# ── DESCARGA SEGMENTADA ───────────────────────────────────────────
def _download_segment(url: str, start: int, end: int, output_path: Path,
                      progress_callback=None, stop_event=None,
                      max_retries: int = 3, retry_delay: float = 2.0) -> bool:
    """Descarga un segmento [start, end] de una URL con soporte Range.
    Reintentar hasta max_retries veces ante errores. Escribe directamente en
    output_path en la posición correcta."""
    for attempt in range(max_retries):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Range": f"bytes={start}-{end}",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=240) as resp:
                with open(output_path, "r+b") as f:
                    f.seek(start)
                    while True:
                        if stop_event and stop_event.is_set():
                            return False
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))
            return True
        except (TimeoutError, urllib.error.URLError) as e:
            logger.warning(
                "segment error %s-%s (attempt %s/%s) — error de red: %s",
                start, end, attempt + 1, max_retries, e,
            )
            if stop_event and stop_event.is_set():
                return False
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
        except Exception as e:
            logger.warning("segment error %s-%s (attempt %s/%s): %s", start, end, attempt + 1, max_retries, e)
            if stop_event and stop_event.is_set():
                return False
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
    return False