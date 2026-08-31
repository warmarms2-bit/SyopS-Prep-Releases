#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  RESOLVER GATEWAY - Puerta de acceso al paquete privado resolver_pack/
#
#  Carga resolver_pack/ de forma diferida. Si el paquete está presente,
#  expone las capacidades reales de resolución. Si NO está (repo público
#  sin el bundle), expone stubs inofensivos: el wizard corre con aviso y
#  todo lo demás (catalogar, planificar, validar, UI) sigue funcionando.
#
#  Ningún otro módulo del repo público debe importar resolver_pack* de
#  forma directa: todo pasa por este gateway.
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Override para tests/CI: fuerza la rama "sin resolver_pack" aunque el
# paquete privado esté presente en el entorno.
_FORCE_NO_PACK = os.environ.get("SYOPS_NO_RESOLVER_PACK", "") in ("1", "true", "True")

# TorBox (debrid) es un módulo PÚBLICO en services/ (API genérica de
# torbox.app, sin know-how privado): siempre disponible, dormido por defecto
# (requiere TORBOX_ENABLED + TORBOX_TOKEN). Al activarlo reemplaza el flujo
# torrent (el cliente nunca entra al swarm).
from services import torbox_provider as _torbox
torbox = _torbox

try:  # resolver_pack presente (bundle del cliente / entorno privado)
    if _FORCE_NO_PACK:
        raise ImportError("SYOPS_NO_RESOLVER_PACK forzado (simula repo público)")
    from resolver_pack import api as _api
    from resolver_pack import download_helpers as _helpers  # noqa: F401
    from resolver_pack.torrent_downloader import TorrentDownloader

    HAS_RESOLVER_PACK = True

    _resolve_download_link = _api._resolve_download_link
    URL_RESOLVERS = list(_api.URL_RESOLVERS)

    # Resolvers del pack (pueden requerir workers/navegador).
    is_akirabox_url = _api.is_akirabox_url
    is_appstorrent_url = _api.is_appstorrent_url
    is_swisstransfer_url = _api.is_swisstransfer_url
    is_workupload_url = _api.is_workupload_url
    is_pixeldrain_url = _api.is_pixeldrain_url
    is_seyarabata_url = _api.is_seyarabata_url

    make_akirabox_resolver = _api.make_akirabox_resolver
    make_swisstransfer_resolver = _api.make_swisstransfer_resolver
    make_seyarabata_resolver = _api.make_seyarabata_resolver
    make_pixeldrain_resolver = _api.make_pixeldrain_resolver
    make_workupload_resolver = _api.make_workupload_resolver
    make_appstorrent_resolver = _api.make_appstorrent_resolver

    _pixeldrain_file_id = _api._pixeldrain_file_id
    _pixeldrain_file_info = _api._pixeldrain_file_info
    _pixeldrain_direct_url = _api._pixeldrain_direct_url
    _resolve_pixeldrain_download_url = _api._resolve_pixeldrain_download_url
    pixeldrain_resolved_metadata = _api.pixeldrain_resolved_metadata
    PIXELDRAIN_BYPASS_HOSTS = tuple(_api.PIXELDRAIN_BYPASS_HOSTS)

except Exception as exc:  # sin resolver_pack: stubs funcionales
    HAS_RESOLVER_PACK = False
    logger.debug("resolver_pack no presente (%s); usando stubs.", exc)

    # Resolvers PÚBLICOS: funcionan sin el pack privado.
    # Pixeldrain (bypass/API), SwissTransfer (API REST), Seyarabata (302),
    # Workupload (session+puzzle) usan stdlib puro. AkiraBox y Appstorrent
    # arrancan su worker QWebEngine en un subprocess (requieren PySide6 en
    # runtime, presente en la instalación real).
    from services.public_resolvers import (  # noqa: F401
        PIXELDRAIN_BYPASS_HOSTS,
        _pixeldrain_direct_url,
        _pixeldrain_file_id,
        _pixeldrain_file_info,
        _resolve_pixeldrain_download_url,
        is_akirabox_url,
        is_appstorrent_url,
        is_pixeldrain_url,
        is_seyarabata_url,
        is_swisstransfer_url,
        is_workupload_url,
        make_akirabox_resolver,
        make_appstorrent_resolver,
        make_pixeldrain_resolver,
        make_seyarabata_resolver,
        make_swisstransfer_resolver,
        make_workupload_resolver,
        pixeldrain_resolved_metadata,
        resolver_factories,
    )
    from services.public_resolvers import (
        URL_RESOLVERS as _PUBLIC_URL_RESOLVERS,
    )

    def _resolve_download_link(app: str) -> tuple:
        """Sin el pack privado no hay links configurados → método manual."""
        return "manual", ""

    URL_RESOLVERS: list = list(_PUBLIC_URL_RESOLVERS)

    class TorrentDownloader:
        """Stub: sin el pack privado no hay clientes torrent."""

        def __init__(self, *args, **kwargs):
            pass

        def _emit_completed(self, name, success, size):
            pass

        async def download_torrent(self, name: str, magnet: str, dest_dir):
            """Descarga torrent con libtorrent si está disponible."""
            from app_config import DHT_NODES
            try:
                import libtorrent as lt
            except ImportError:
                logger.warning("[TORRENT] libtorrent no disponible para %s", name)
                self._emit_completed(name, False, 0)
                return
            try:
                ses = lt.session()
                ses.listen_on(6881, 6891)
                for node in DHT_NODES:
                    try:
                        ses.add_dht_node(node)
                    except Exception:
                        pass
                ses.start_dht()
                params = lt.parse_magnet_uri(magnet)
                params.save_path = str(dest_dir)
                handle = ses.add_torrent(params)
                handle.set_max_connections(200)
                handle.resume()
                import asyncio
                while not handle.is_seed():
                    status = handle.status()
                    if status.state == lt.torrent_status.seeding:
                        break
                    await asyncio.sleep(1)
                self._emit_completed(name, True, handle.status().total_done)
            except Exception as e:
                logger.error("[TORRENT] Error descargando %s: %s", name, e)
                self._emit_completed(name, False, 0)


# ── Resolución por kind (server-driven, lazy por app) ─────────────
# El servidor (SYOPS_LINK_SERVER) indica qué tipo de resolver usa cada
# app vía el campo `resolver`. El wizard activa SOLO ese resolver vía
# get_resolver(kind), sin tocar los otros hosts ni iterar URL_RESOLVERS.

RESOLVER_KINDS = {
    "akirabox": "make_akirabox_resolver",
    "swisstransfer": "make_swisstransfer_resolver",
    "workupload": "make_workupload_resolver",
    "pixeldrain": "make_pixeldrain_resolver",
    "seyarabata": "make_seyarabata_resolver",
    "appstorrent": "make_appstorrent_resolver",
}

# Todos los kinds tienen soporte sin el pack privado (services/public_resolvers.py).
# El pack sigue disponible y tiene prioridad para sus propios resolvers.
_PACK_ONLY_RESOLVERS = ()


def _normalize_kind(kind) -> str:
    """Normaliza el hint del sheet: minúsculas y sin espacios externos.

    La celda `resolver` puede traer "Pixeldrain", " pixeldrain " etc.; se
    tolera para no romper la descarga por un typo de mayúsculas/espacios.
    """
    return (str(kind or "")).strip().lower()


def has_resolver(kind: str) -> bool:
    """True si `kind` está disponible en este entorno.

    Todos los kinds (pixeldrain, swisstransfer, seyarabata, workupload,
    akirabox, appstorrent) tienen soporte PÚBLICO en
    services/public_resolvers.py: disponibles también sin el pack privado.
    """
    kind = _normalize_kind(kind)
    if kind in RESOLVER_KINDS and kind not in _PACK_ONLY_RESOLVERS:
        return True
    if not HAS_RESOLVER_PACK:
        return False
    return kind in RESOLVER_KINDS


def get_resolver(kind: str, link: str, app: str | None = None, **kwargs):
    """Devuelve un resolver_callback para `kind` (activación lazy por app).

    Solo crea el callback del resolver pedido; no se instancia ningún otro.
    Los kinds usan el soporte de services/public_resolvers.py; con el pack
    presente los factories del pack tienen prioridad.
    """
    kind = _normalize_kind(kind)
    if kind in RESOLVER_KINDS and kind not in _PACK_ONLY_RESOLVERS:
        kwargs.setdefault("link", link)
        if app is not None:
            kwargs.setdefault("app", app)
        factory = globals()[RESOLVER_KINDS[kind]]
        return factory(**kwargs)
    if not HAS_RESOLVER_PACK:
        raise RuntimeError(
            "resolver_pack no disponible en este entorno: no se puede "
            "resolver la descarga."
        )
    factory_name = RESOLVER_KINDS.get(kind)
    if factory_name is None:
        raise ValueError(f"resolver desconocido: {kind!r}")
    factory = getattr(_api, factory_name)
    kwargs.setdefault("link", link)
    if app is not None:
        kwargs.setdefault("app", app)
    return factory(**kwargs)