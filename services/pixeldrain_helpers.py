#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  PIXELDRAIN HELPERS - Soporte público de descargas Pixeldrain
#
#  Estas funciones NO dependen del paquete privado resolver_pack:
#  se usan también cuando el pack no está instalado (repo público /
#  instalación one-liner), para que los links de Pixeldrain de la hoja
#  se resuelvan por bypass o por API directa en lugar de bajar la
#  página HTML de vista (/u/<id>).
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import logging

from services.http_utils import (
    _filename_from_content_disposition,
)

logger = logging.getLogger(__name__)

PIXELDRAIN_BYPASS_HOSTS = [
    # CDN del bypass de GameDrive: rota a cdnNN.pixeldrain.eu.cc y sirve el
    # archivo real sin el límite de pixeldrain.
    "cdn.pixeldrain.eu.cc",
    "pixeldrain.isuru.eu.org",
    "pixeldrain-bypass.gamedrive.org",
]


def _pixeldrain_file_id(url: str) -> str:
    """Extrae el ID de archivo de una URL de Pixeldrain (/u/<id> o /api/file/<id>).
    Devuelve el ID o cadena vacía si no es Pixeldrain."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in ("pixeldrain.com", "www.pixeldrain.com"):
        return ""
    for pattern in (r"/u/([a-zA-Z0-9_-]+)", r"/api/file/([a-zA-Z0-9_-]+)"):
        m = re.match(pattern, parsed.path)
        if m:
            return m.group(1)
    return ""


def is_pixeldrain_url(url: str) -> bool:
    """Detector uniforme para el registro de resolvers."""
    return bool(_pixeldrain_file_id(url))


def _pixeldrain_direct_url(url: str) -> str:
    """Convierte una URL de vista (pixeldrain.com/u/<id>) en la URL de la API
    directa (pixeldrain.com/api/file/<id>). Si no es pixeldrain, devuelve original."""
    file_id = _pixeldrain_file_id(url)
    if not file_id:
        return url
    return f"https://pixeldrain.com/api/file/{file_id}"


def _pixeldrain_file_info(url: str) -> tuple:
    """Consulta la API de Pixeldrain: (nombre, tamaño_bytes, sha256) o (None, 0, None)."""
    try:
        file_id = _pixeldrain_file_id(url)
        if not file_id:
            return None, 0, None
        info_url = f"https://pixeldrain.com/api/file/{file_id}/info"
        req = urllib.request.Request(
            info_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("success"):
            return data.get("name"), int(data.get("size", 0) or 0), data.get("hash_sha256")
    except Exception as e:
        logger.warning("error consultando info: %s", e)
    return None, 0, None


def _resolve_pixeldrain_download_url(url: str) -> tuple:
    """Resuelve una URL de Pixeldrain a la URL final efectiva para descargar.

    Primero intenta los bypass mirrors (evitan el límite de 6GB/día). Si
    fallan, cae a la API directa de Pixeldrain. Devuelve
    (final_url, total_size, supports_range, filename_hint).
    """
    if not url:
        return None, 0, False, ""
    file_id = _pixeldrain_file_id(url)
    if not file_id:
        # No es Pixeldrain: HEAD para averiguar tamaño y soporte de Range.
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                total = int(resp.headers.get("content-length", 0) or 0)
                cd_name = _filename_from_content_disposition(
                    resp.headers.get("content-disposition", "")
                )
                supports_range = resp.headers.get("accept-ranges", "").lower() == "bytes"
                return url, total, supports_range, cd_name
        except Exception:
            pass
        return url, 0, False, ""

    # Probar bypass mirrors en orden aleatorio.
    bypass_hosts = list(PIXELDRAIN_BYPASS_HOSTS)
    random.shuffle(bypass_hosts)
    for host in bypass_hosts:
        bypass_url = f"https://{host}/{file_id}"
        try:
            req = urllib.request.Request(
                bypass_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                final_url = resp.geturl()
                total = int(resp.headers.get("content-length", 0) or 0)
                content_type = resp.headers.get("content-type", "")
                cd_name = _filename_from_content_disposition(
                    resp.headers.get("content-disposition", "")
                )
                supports_range = resp.headers.get("accept-ranges", "").lower() == "bytes"
                # Validar que realmente sea el archivo (no HTML/Cloudflare).
                if total > 0 and not content_type.startswith("text/html"):
                    logger.info("using bypass %s -> %s (%s bytes)", host, final_url, total)
                    return final_url, total, supports_range, cd_name
        except Exception as e:
            logger.warning("bypass %s failed for %s: %s", host, file_id, e)

    # Fallback a la API directa de Pixeldrain.
    direct_url = f"https://pixeldrain.com/api/file/{file_id}?download"
    try:
        req = urllib.request.Request(
            direct_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            total = int(resp.headers.get("content-length", 0) or 0)
            cd_name = _filename_from_content_disposition(
                resp.headers.get("content-disposition", "")
            )
            supports_range = resp.headers.get("accept-ranges", "").lower() == "bytes"
            logger.info("using direct API for %s (%s bytes)", file_id, total)
            return resp.geturl(), total, supports_range, cd_name
    except Exception as e:
        logger.warning("direct API failed for %s: %s", file_id, e)
    return None, 0, False, ""


def pixeldrain_resolved_metadata(resolved_url: str) -> tuple:
    """HEAD request a un link resuelto de Pixeldrain para obtener metadata.
    Sincrona: ejecutar via asyncio.to_thread para no bloquear el loop."""
    req = urllib.request.Request(
        resolved_url,
        headers={"User-Agent": "Mozilla/5.0"},
        method="HEAD",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        total = int(resp.headers.get("content-length", 0) or 0)
        cd_name = _filename_from_content_disposition(
            resp.headers.get("content-disposition", "")
        )
        supports_range = resp.headers.get("accept-ranges", "").lower() == "bytes"
    return total, cd_name, supports_range


def _download_segment(
    url: str,
    start: int,
    end: int,
    output_path: Path,
    progress_callback=None,
    stop_event=None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> bool:
    """Descarga un segmento [start, end] con Range. Reintenta hasta max_retries."""
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
            logger.warning(
                "segment error %s-%s (attempt %s/%s): %s",
                start, end, attempt + 1, max_retries, e,
            )
            if stop_event and stop_event.is_set():
                return False
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
    return False