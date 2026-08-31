import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

from services.download_config import TORBOX_API

# Hoster cubiertos por el debrid de TorBox (tabla "Debrid Hosters" de TorBox).
# Fuera de esta lista (pixeldrain, workupload, etc.) TorBox NO baja el archivo:
# esos links quedan en el flujo resolver -> directo del cliente.
TORBOX_SUPPORTED_HOSTS = {
    "hotlink.cc", "oboom.io", "daofile.com", "devuploads.com", "elitefile.net",
    "fastfile.cc", "filejoker.net", "filesmonster.com", "k2s.cc", "moondl.com",
    "novafile.org", "takefile.link", "twojplik.to", "uploadgig.com",
}


def _host_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def torbox_supports(url: str) -> bool:
    """¿TorBox puede debridiar esta URL?

    Los magnets siempre (TorBox entra al swarm por vos). Los hosters sólo si su
    dominio está en ``TORBOX_SUPPORTED_HOSTS``; si no (p.ej. pixeldrain o
    workupload) NO usar TorBox y quedarse en el resolver -> directo del cliente.
    """
    if url.startswith("magnet:"):
        return True
    return _host_of(url) in TORBOX_SUPPORTED_HOSTS

POLL_INTERVAL = 3
POLL_TIMEOUT = 600
CACHE_FILE = None


def torbox_enabled() -> bool:
    """¿TorBox está activado? Lee el env en CADA llamada (no al importar).

    ``TORBOX_ENABLED=1`` + ``TORBOX_TOKEN`` configurado. Apagado por
    defecto: sin estas vars el flujo actual (torrent/http directo) queda
    intacto. Al activarlo, TorBox REEMPLAZA el flujo (el cliente nunca
    entra al swarm de torrents).
    """
    token = os.environ.get("TORBOX_TOKEN", "").strip()
    enabled = os.environ.get("TORBOX_ENABLED", "").strip().lower() in ("1", "true")
    return bool(enabled and token)


def set_cache_file(path: Path):
    global CACHE_FILE
    CACHE_FILE = path

def _get_token(token: str = None) -> str:
    if token:
        return token
    token = os.environ.get("TORBOX_TOKEN", "").strip()
    if token:
        return token
    if CACHE_FILE and CACHE_FILE.exists():
        data = json.loads(CACHE_FILE.read_text())
        return data.get("torbox_token", "")
    return ""

def _api(method: str, endpoint: str, data: dict = None, token: str = None):
    url = f"{TORBOX_API}{endpoint}"
    token = _get_token(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        raise Exception(f"TorBox API error {e.code}: {body}")

def add_magnet(magnet: str, token: str = None) -> str:
    result = _api("POST", "/torrents/createtorrent", {"magnet": magnet}, token)
    if result.get("success") and result.get("data"):
        return result["data"].get("torrent_id", "")
    raise Exception(f"TorBox add_magnet failed: {result}")

def add_url(url: str, token: str = None) -> str:
    result = _api("POST", "/torrents/createtorrent", {"link": url}, token)
    if result.get("success") and result.get("data"):
        return result["data"].get("torrent_id", "")
    raise Exception(f"TorBox add_url failed: {result}")

def get_status(torrent_id: str, token: str = None) -> dict:
    result = _api("GET", "/torrents/mylist", token=token)
    if result.get("success") and result.get("data"):
        for t in result["data"]:
            if str(t.get("id", "")) == str(torrent_id):
                return t
    return {}

def wait_for_completion(torrent_id: str, token: str = None, on_progress=None):
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        status = get_status(torrent_id, token)
        if not status:
            time.sleep(POLL_INTERVAL)
            continue
        progress = status.get("progress", 0)
        name = status.get("name", "?")
        if on_progress:
            on_progress(name, progress)
        if status.get("download_present"):
            return status
        if status.get("cached") and status.get("download_present"):
            return status
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"TorBox torrent {torrent_id} timed out after {POLL_TIMEOUT}s")

def get_download_url(status: dict) -> str:
    return status.get("download_url", "")

def resolve_to_direct_url(link_or_magnet: str, token: str = None, on_progress=None) -> dict:
    is_magnet = link_or_magnet.startswith("magnet:")
    torrent_id = add_magnet(link_or_magnet, token) if is_magnet else add_url(link_or_magnet, token)
    status = wait_for_completion(torrent_id, token, on_progress)
    download_url = get_download_url(status)
    return {
        "torrent_id": torrent_id,
        "download_url": download_url,
        "name": status.get("name", ""),
        "size": status.get("size", 0),
    }
