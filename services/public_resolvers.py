#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  PUBLIC RESOLVERS - Resolvers de descarga SIN paquete privado
#
#  Implementa los resolvers que únicamente requieren stdlib (urllib,
#  http.client, hashlib, cookiejar) para que funcionen en el repo público
#  y en la instalación one-liner, sin depender de resolver_pack.
#
#  Cada resolver expone:
#     - is_<host>_url(url)      → detector
#     - make_<host>_resolver(link, **kwargs) → factory de resolver_callback
#       (callable () -> (url_final, headers_extra))
#
#  Los resolvers que necesitan navegador / workers (akirabox, appstorrent)
#  NO van acá: siguen en el pack privado.
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations

import hashlib
import http.client
import http.cookiejar
import json
import logging
import re
import time
import urllib.parse
import urllib.request

from services.pixeldrain_helpers import (  # noqa: F401  (re-export)
    PIXELDRAIN_BYPASS_HOSTS,
    _pixeldrain_direct_url,
    _pixeldrain_file_id,
    _pixeldrain_file_info,
    _resolve_pixeldrain_download_url,
    pixeldrain_resolved_metadata,
)

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


# ── Pixeldrain (proxy por pixeldrain_helpers) ──────────────────────
def is_pixeldrain_url(url: str) -> bool:
    return bool(_pixeldrain_file_id(url))


def make_pixeldrain_resolver(link: str, **kwargs):
    """Transformación de URL instantánea (sin I/O)."""
    def resolve() -> tuple[str, dict[str, str]]:
        return _pixeldrain_direct_url(link), {}
    return resolve


# ── SwissTransfer (API REST pública) ───────────────────────────────
SWISSTRANSFER_HOSTS = ("swisstransfer.com",)


def is_swisstransfer_url(url: str) -> bool:
    if not url:
        return False
    try:
        netloc = urllib.parse.urlparse(url).hostname
    except Exception:
        return False
    if not netloc:
        return False
    return any(netloc == h or netloc.endswith("." + h) for h in SWISSTRANSFER_HOSTS)


def _swisstransfer_link_uuid(url: str) -> str:
    m = re.search(r"swisstransfer\.com/d/([a-f0-9-]+)", url, re.IGNORECASE)
    return m.group(1) if m else ""


def _swisstransfer_link_info(link_uuid: str) -> dict:
    api_url = f"https://www.swisstransfer.com/api/links/{link_uuid}"
    req = urllib.request.Request(api_url, headers=_ua_headers())
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    if data.get("result") != "success":
        raise ValueError(f"API error: {data}")
    return data.get("data", {})


def _swisstransfer_download_token(container_uuid: str, file_uuid: str,
                                  password: str = "") -> str:
    api_url = "https://www.swisstransfer.com/api/generateDownloadToken"
    payload = json.dumps({
        "containerUUID": container_uuid,
        "fileUUID": file_uuid,
        "password": password,
    }).encode("utf-8")
    req = urllib.request.Request(api_url, data=payload, headers={
        **_ua_headers(),
        "Content-Type": "application/json",
    })
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        raise ValueError(f"Respuesta inesperada: {data!r}")
    inner = data.get("data", data)
    token = inner.get("token", "") if isinstance(inner, dict) else ""
    if not token:
        raise ValueError(f"generateDownloadToken sin token: {data!r}")
    return token


def resolve_swisstransfer_url(url: str, timeout: int = 30, retries: int = 2) -> str:
    """Resuelve una URL de SwissTransfer a la URL de descarga directa."""
    if not is_swisstransfer_url(url):
        return ""
    link_uuid = _swisstransfer_link_uuid(url)
    if not link_uuid:
        logger.error("No se pudo extraer link UUID de: %s", url)
        return ""
    for attempt in range(retries + 1):
        try:
            info = _swisstransfer_link_info(link_uuid)
            container = info.get("container", {})
            files = container.get("files", [])
            if not files:
                logger.warning("No se encontraron archivos en %s", link_uuid)
                return ""
            best = (max(files, key=lambda f: f.get("fileSizeInBytes", 0))
                    if len(files) > 1 else files[0])
            file_uuid = best.get("UUID", "")
            container_uuid = container.get("UUID", "")
            if not file_uuid or not container_uuid:
                logger.warning("UUIDs faltantes")
                return ""
            token = _swisstransfer_download_token(container_uuid, file_uuid)
            return (f"https://www.swisstransfer.com/api/download/"
                    f"{link_uuid}/{file_uuid}?token={token}")
        except Exception as e:
            logger.warning("Error (attempt %s): %s", attempt + 1, e)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    return ""


def make_swisstransfer_resolver(link: str, **kwargs):
    def resolve() -> tuple[str, dict[str, str]]:
        result = resolve_swisstransfer_url(link)
        if not result:
            raise RuntimeError("SwissTransfer no disponible")
        return result, {}
    return resolve


# ── Seyarabata (302 a dl.seyarabata.com) ───────────────────────────
SEYARABATA_HOST = "seyarabata.com"


def is_seyarabata_url(url: str) -> bool:
    if not url:
        return False
    try:
        netloc = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    return netloc == SEYARABATA_HOST or netloc.endswith("." + SEYARABATA_HOST)


def _seyarabata_file_id(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"/(?:u|t|d/)?([A-Za-z0-9]{8,})/?$", url)
    return m.group(1) if m else ""


def resolve_seyarabata_url(url: str, timeout: int = 30, retries: int = 1) -> str:
    """Convierte un link de seyarabata en la URL directa del archivo."""
    if not is_seyarabata_url(url):
        return url
    file_id = _seyarabata_file_id(url)
    if not file_id:
        return ""
    direct = f"https://{SEYARABATA_HOST}/d/{file_id}"
    for _ in range(retries + 1):
        try:
            parsed = urllib.parse.urlparse(direct)
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
            conn.request("GET", parsed.path, headers={"User-Agent": _UA})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.getheader("Location", "")
                conn.close()
                if loc and "dl.seyarabata.com" in loc:
                    return loc
            conn.close()
        except Exception as e:
            logger.warning("seyarabata resolve error: %s", e)
            continue
    return ""


def make_seyarabata_resolver(link: str, **kwargs):
    def resolve() -> tuple[str, dict[str, str]]:
        result = resolve_seyarabata_url(link)
        if not result:
            raise RuntimeError("Seyarabata no disponible")
        return result, {}
    return resolve


# ── Workupload (session + puzzle + token) ──────────────────────────
WORKUPLOAD_HOSTS = ("workupload.com",)


def is_workupload_url(url: str) -> bool:
    if not url:
        return False
    try:
        netloc = urllib.parse.urlparse(url).hostname
    except Exception:
        return False
    if not netloc:
        return False
    return any(netloc == h or netloc.endswith("." + h) for h in WORKUPLOAD_HOSTS)


def _workupload_file_id(url: str) -> str:
    m = re.search(r"workupload\.com/(?:file|archive)/([a-zA-Z0-9_-]+)",
                  url, re.IGNORECASE)
    return m.group(1) if m else ""


def _workupload_solve_puzzle(puzzle_data: dict) -> str:
    puzzle = puzzle_data["data"]["puzzle"]
    find_hashes = puzzle_data["data"]["find"]
    range_val = puzzle_data["data"]["range"]
    solutions = []
    for i in range(range_val):
        test = puzzle + str(i)
        if hashlib.sha256(test.encode()).hexdigest() in find_hashes:
            solutions.append(str(i))
    return " ".join(solutions)


def _workupload_open(opener, url, timeout, data=None):
    return opener.open(url, data=data, timeout=timeout)


def resolve_workupload_with_session(url: str, timeout: int = 30,
                                    retries: int = 2) -> tuple:
    """Resuelve una URL de Workupload → (download_url, cookie_str)."""
    if not is_workupload_url(url):
        return ("", None)
    file_id = _workupload_file_id(url)
    if not file_id:
        logger.error("No se pudo extraer file ID de: %s", url)
        return ("", None)
    for attempt in range(retries + 1):
        try:
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cj))
            opener.addheaders = [("User-Agent", _UA)]

            resp = _workupload_open(opener, "https://workupload.com/puzzle", timeout)
            puzzle_data = json.loads(resp.read().decode())
            captcha = _workupload_solve_puzzle(puzzle_data)

            post_data = urllib.parse.urlencode({"captcha": captcha}).encode()
            req = urllib.request.Request(
                "https://workupload.com/captcha",
                data=post_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            _workupload_open(opener, req, timeout)
            _workupload_open(opener, f"https://workupload.com/start/{file_id}", timeout)

            resp = _workupload_open(
                opener,
                f"https://workupload.com/api/file/getDownloadServer/{file_id}",
                timeout,
            )
            data = json.loads(resp.read().decode())
            download_url = data.get("data", {}).get("url", "")
            if not download_url:
                raise ValueError("No se pudo obtener URL de descarga")

            cookie_str = ""
            for c in cj:
                if c.name == "token":
                    cookie_str = f"token={c.value}"
                    break
            return (download_url, cookie_str)
        except Exception as e:
            logger.warning("Error (attempt %s): %s", attempt + 1, e)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    return ("", None)


def make_workupload_resolver(link: str | None = None, original_url: str | None = None,
                             retries: int = 2, timeout: int = 30, **kwargs):
    """Factory: (url, headers_extra con Cookie + Referer)."""
    url = link or original_url or ""

    def resolve() -> tuple[str, dict[str, str]]:
        download_url, cookie_str = resolve_workupload_with_session(url, timeout, retries)
        if not download_url:
            raise RuntimeError("No se pudo resolver Workupload")
        return download_url, {
            "Cookie": cookie_str,
            "Referer": "https://workupload.com/",
        }
    return resolve


# ── Registro central de resolvers públicos ─────────────────────────
# kind → {"is": detector, "make": factory}. Úsalo para has_resolver /
# get_resolver sin el pack privado.
PUBLIC_RESOLVERS = {
    "pixeldrain": {"is": is_pixeldrain_url, "make": make_pixeldrain_resolver},
    "swisstransfer": {"is": is_swisstransfer_url, "make": make_swisstransfer_resolver},
    "seyarabata": {"is": is_seyarabata_url, "make": make_seyarabata_resolver},
    "workupload": {"is": is_workupload_url, "make": make_workupload_resolver},
}


def resolver_factories(kind: str) -> tuple:
    """Devuelve (make, is_url) para un kind público, o (None, None)."""
    entry = PUBLIC_RESOLVERS.get(kind)
    if not entry:
        return None, None
    return entry["make"], entry["is"]


# ── URL_RESOLVERS (para el flujo local, sin repo de links) ─────────
URL_RESOLVERS = [
    (is_pixeldrain_url, make_pixeldrain_resolver),
    (is_swisstransfer_url, make_swisstransfer_resolver),
    (is_seyarabata_url, make_seyarabata_resolver),
    (is_workupload_url, make_workupload_resolver),
]


def _ua_headers() -> dict:
    return {"User-Agent": _UA, "Accept": "application/json"}