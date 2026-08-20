APP_VERSION = "1.3.22"
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

# ── URLs DE DESCARGA ──────────────────────────────────────────────
GENP_URL = "https://gen.paramore.su/GenP.v3.8.0-CGP.zip"
RUSTDESK_URL = "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.msi"
RUSTDESK_URL_MAC = "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-aarch64.dmg"
SEVENZIP_URL = "https://www.7-zip.org/a/7z2409-x64.exe"
SEVENZIP_URL_32 = "https://www.7-zip.org/a/7z2409.exe"

# ── WHATSAPP ──────────────────────────────────────────────────────
WHATSAPP_NUMBER = "51955242837"

# ── DIRECTORIO DE TRABAJO ─────────────────────────────────────────
import os
import sys
from pathlib import Path


def _resolve_syops_dir() -> Path:
    """Directorio de estado/descargas.

    En Windows se intenta C:\\SYOPS (compartido con la UI); si la raíz del
    disco no es escribible (usuario sin permisos de admin), se cae a un
    directorio del usuario para no romper el wizard con PermissionError.
    """
    if sys.platform == "win32":
        candidate = Path(f"{os.environ.get('SystemDrive', 'C:')}/SYOPS")
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            base = os.environ.get("LOCALAPPDATA") or str(Path.home())
            return Path(base) / "SYOPS"
    return Path(os.path.expanduser("~/SYOPS"))


SYOPS_DIR = _resolve_syops_dir()

# ── URLs EXTERNAS (sobreescribibles por env vars) ──────────────────
UPDATE_CHECK_URL = os.environ.get(
    "SYOPS_UPDATE_URL",
    "https://gist.githubusercontent.com/warmarms2-bit/e7c5bd0041d5082fdbd196842a043a55/raw/version.json",
)
SHEETS_URL = os.environ.get(
    "SYOPS_SHEETS_URL",
    "https://script.google.com/macros/s/AKfycbyti1-M-64wiN0NfAiuTv3QRz0-ZTmYhZLo22T7GmQdMa2DvRTU7qxcaMRrA-e30IS1/exec",
)
LINK_SERVER_URL = os.environ.get(
    "SYOPS_LINK_SERVER",
    "https://script.google.com/macros/s/AKfycbyti1-M-64wiN0NfAiuTv3QRz0-ZTmYhZLo22T7GmQdMa2DvRTU7qxcaMRrA-e30IS1/exec",
)

# ── RED: TORRENT (DHT nodes + trackers públicos) ──────────────────
# Configuración de red para descarga por torrent. Editable sin tocar
# la lógica del motor de descargas.
DHT_NODES = [
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881),
    ("dht.libtorrent.org", 25401),
    ("tracker.opentrackr.org", 1337),
    ("open.tracker.cl", 1337),
    ("tracker.openbittorrent.com", 6969),
    ("open.stealth.si", 80),
    ("tracker.torrent.eu.org", 451),
    ("tracker.tiny-vps.com", 6969),
]

TORRENT_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "http://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://tracker.cyberia.is:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker2.dler.org:80/announce",
    "udp://tracker-udp.gbitt.info:80/announce",
    "http://tracker.gbitt.info:80/announce",
    "udp://tracker.0x.tf:6969/announce",
    "udp://tracker.army:6969/announce",
    "udp://tracker.torrent.trade:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.empire-host.vip:6969/announce",
    "udp://tracker.birkenwald.de:6969/announce",
    "udp://tracker.beeimg.com:6969/announce",
    "udp://tracker.bt4g.com:2095/announce",
    "http://tracker.bt4g.com:2095/announce",
    "udp://opentracker.io:6969/announce",
    "udp://tracker1.mypn.top:6869/announce",
    "udp://tracker-udp.ozucfxi.com:6969/announce",
    "udp://tracker.auctor.tv:6969/announce",
    "udp://tracker.fnix.net:6969/announce",
    "udp://tracker.tryhackx.org:6969/announce",
    "udp://tracker.gmi.gd:6969/announce",
    "udp://tracker.therarbg.to:6969/announce",
    "udp://tracker.torrust-demo.com:6969/announce",
    "udp://tracker.filemail.com:6969/announce",
    "https://tracker.moeblog.cn:443/announce",
    "https://tracker.lilithraws.org:443/announce",
    "https://tracker.itscraftsoftware.my.id:443/announce",
    "https://tr.nyacat.pw:443/announce",
    "udp://tracker.54durn.top:6969/announce",
    "udp://wepzone.net:6969/announce",
    "udp://ttk2.nbaonlineservice.com:6969/announce",
    "udp://tracker.xor.st:6969/announce",
    "udp://tracker.safe.moe:6969/announce",
    "udp://retracker01-msk-ru.xpond.ru:6969/announce",
    "udp://public.tracker.vuze.com:6969/announce",
]

# ── RED: TORBOX (debrid) ───────────────────────────────────────────
TORBOX_API = "https://api.torbox.app/v1/api"

# ── SEGURIDAD: verificación externa ────────────────────────────────
# URL de VirusTotal que verifica el instalador de la app (se muestra
# en la página de inicio como enlace de transparencia).
VIRUSTOTAL_VERIFY_URL = "https://www.virustotal.com/gui/file/210f1910a373e237224f352dd3bc2093f455462c71ae305f56d2086a1131be18?nocache=1"
