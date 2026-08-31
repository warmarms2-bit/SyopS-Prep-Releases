import os
import sys
from pathlib import Path

APP_VERSION = "1.3.90"
WHATSAPP_DISPLAY = "+51 955 242 837"

# ── CONFIGURACION GENERAL ─────────────────────────────────────────
MAX_APPS = 99  # Maximo de programas que el cliente puede seleccionar (full pack)
DEFAULT_APPS = 3  # Límite por defecto sin activación
MAX_CONCURRENT = 3

# ── TAMAÑO DE VENTANA (fuente de verdad) ──────────────────────────
# La app abre a estos tamaños; los widgets responsive (ej. mascota del
# sidebar) usan WIN_HEIGHT para recalcular al redimensionar.
WIN_WIDTH = 950
WIN_HEIGHT = 700
WIN_MIN_WIDTH = 750
WIN_MIN_HEIGHT = 600
SIDEBAR_WIDTH = 200  # ancho del sidebar

# ── URLs DE DESCARGA (pinneadas a propósito: reproducibles; sobreescribibles
#    por env para bump sin tocar código — el Quality Gate avisa si están viejas)
GENP_URL = os.environ.get("SYOPS_GENP_URL",
                          "https://gen.paramore.su/GenP.v3.8.0-CGP.zip")
RUSTDESK_URL = os.environ.get(
    "SYOPS_RUSTDESK_URL",
    "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.msi")
RUSTDESK_URL_MAC = os.environ.get(
    "SYOPS_RUSTDESK_URL_MAC",
    "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-aarch64.dmg")
SEVENZIP_URL = os.environ.get("SYOPS_SEVENZIP_URL",
                              "https://www.7-zip.org/a/7z2409-x64.exe")
SEVENZIP_URL_32 = os.environ.get("SYOPS_SEVENZIP_URL_32",
                                 "https://www.7-zip.org/a/7z2409.exe")

# ── WARP (Cloudflare 1.1.1.1) ─────────────────────────────────────
# Instaladores oficiales. Se usan SOLO si la selección tiene descargas por
# torrent directo (y TorBox no está activo) para ocultar la IP real del
# cliente a los peers. Sobreescribibles por env para fijar versiones.
WARP_URL_MAC = os.environ.get(
    "SYOPS_WARP_URL_MAC",
    "https://1111-releases.cloudflareclient.com/mac/Cloudflare_WARP.pkg")
WARP_URL_WIN = os.environ.get(
    "SYOPS_WARP_URL_WIN",
    "https://1111-releases.cloudflareclient.com/windows/Cloudflare_WARP_Release-x64.msi")

# ── WHATSAPP ──────────────────────────────────────────────────────
WHATSAPP_NUMBER = "51955242837"

# ── DIRECTORIO DE TRABAJO ─────────────────────────────────────────


def _resolve_syops_dir() -> Path:
    """Directorio de estado/descargas.

    Busca el mejor lugar automáticamente:
    1. Variable de entorno SYOPS_DIR (override manual).
    2. Directorio existente con datos previos.
    3. ~/SYOPS (primera vez).
    """
    env = os.environ.get("SYOPS_DIR", "").strip()
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p

    if sys.platform == "win32":
        candidates = [
            Path(f"{os.environ.get('SystemDrive', 'C:')}/SYOPS"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "SYOPS",
            Path.home() / "SYOPS",
        ]
    else:
        candidates = [
            Path.home() / "SYOPS",
            Path.home() / "Downloads" / "SyopS-Prep",
            Path.home() / "Desktop" / "SyopS-Prep",
        ]

    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue

    primary = candidates[0]
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        for c in candidates[1:]:
            try:
                c.mkdir(parents=True, exist_ok=True)
                return c
            except OSError:
                continue
    return Path.home() / "SYOPS"


SYOPS_DIR = _resolve_syops_dir()

# ── URLs EXTERNAS (sobreescribibles por env vars) ──────────────────
UPDATE_CHECK_URL = os.environ.get(
    "SYOPS_UPDATE_URL",
    "https://gist.githubusercontent.com/warmarms2-bit/e7c5bd0041d5082fdbd196842a043a55/raw/version.json",
)
SHEETS_URL = os.environ.get(
    "SYOPS_SHEETS_URL",
    "https://script.google.com/macros/s/AKfycbydOomJfnVeKRR1p4yIwkOV2bQ0x2A8HuRc1C1RLzyUg01k8i9rQyvGZfjwIFusIDBH/exec",
)
LINK_SERVER_URL = os.environ.get(
    "SYOPS_LINK_SERVER",
    "https://script.google.com/macros/s/AKfycbydOomJfnVeKRR1p4yIwkOV2bQ0x2A8HuRc1C1RLzyUg01k8i9rQyvGZfjwIFusIDBH/exec",
)

# ── RED: TORRENT (DHT nodes + trackers públicos) ──────────────────
# Configuración de red para descarga por torrent. Editable sin tocar
# la lógica del motor de descargas.
DHT_NODES = [
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881),
    ("dht.libtorrent.org", 25401),
    ("dht.aelitis.com", 6881),
    ("bttracker.debian.org", 6969),
    ("tracker.openbittorrent.com", 6969),
    ("open.demonii.com", 1337),
    ("tracker.coppersurfer.tk", 6969),
]

TORRENT_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.tracker.cl:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://tracker.monitorit.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://tracker.cyberia.is:6969/announce",
]

# ── RED: TORBOX (debrid) ───────────────────────────────────────────
TORBOX_API = "https://api.torbox.app/v1/api"

# ── SEGURIDAD: verificación externa ────────────────────────────────
# URL de VirusTotal que verifica el instalador de la app (se muestra
# en la página de inicio como enlace de transparencia).
VIRUSTOTAL_VERIFY_URL = "https://www.virustotal.com/gui/file/210f1910a373e237224f352dd3bc2093f455462c71ae305f56d2086a1131be18?nocache=1"
