"""Configuración del motor de descargas (inyectable).

Centraliza TODA la configuración que usan download_engine, download_manager,
torrent_downloader, torbox_provider y los resolvers. Los módulos del motor
importan desde acá en vez de app_config directamente, de modo que el motor
se pueda reutilizar como librería en otra app: solo hay que reemplazar
download_config (o editar los valores acá) sin tocar la lógica.

Los valores por defecto vienen de app_config (SyopS Prep). Una app externa
puede importar este módulo y sobreescribir los atributos, o proveer su
propio módulo download_config.
"""

from app_config import (
    DHT_NODES, TORRENT_TRACKERS, TORBOX_API, MAX_CONCURRENT,
    GENP_URL, RUSTDESK_URL, RUSTDESK_URL_MAC, SEVENZIP_URL, SEVENZIP_URL_32,
)

# ── Red: torrent ───────────────────────────────────────────────────
DHT_NODES = DHT_NODES
TORRENT_TRACKERS = TORRENT_TRACKERS

# ── Red: TorBox (debrid) ───────────────────────────────────────────
TORBOX_API = TORBOX_API

# ── Concurrencia ───────────────────────────────────────────────────
MAX_CONCURRENT = MAX_CONCURRENT

# ── URLs de herramientas ───────────────────────────────────────────
GENP_URL = GENP_URL
RUSTDESK_URL = RUSTDESK_URL
RUSTDESK_URL_MAC = RUSTDESK_URL_MAC
SEVENZIP_URL = SEVENZIP_URL
SEVENZIP_URL_32 = SEVENZIP_URL_32

# ── Timeouts (segundos) ────────────────────────────────────────────
HTTP_TIMEOUT = 240        # timeout de lectura de urlopen en descargas
RESOLVER_TIMEOUT = 120    # resolución de links (akirabox/swisstransfer)
STALL_TIMEOUT_HTTP = 300      # sin avance de bytes = estancada (HTTP)
STALL_TIMEOUT_TORRENT = 600   # idem para torrent

# ── Descarga por segmentos (pixeldrain) ────────────────────────────
PIXELDRAIN_SEGMENTS = 4
SEGMENT_CHUNK = 262144
