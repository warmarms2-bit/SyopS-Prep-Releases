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

logger = logging.getLogger(__name__)

try:  # resolver_pack presente (bundle del cliente / entorno privado)
    from resolver_pack import api as _api                      # noqa: F401
    from resolver_pack.torrent_downloader import TorrentDownloader
    import resolver_pack.torbox_provider as _torbox
    from resolver_pack import download_helpers as _helpers    # noqa: F401

    HAS_RESOLVER_PACK = True

    _resolve_download_link = _api._resolve_download_link
    URL_RESOLVERS = list(_api.URL_RESOLVERS)

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
    make_appstorrent_resolver = _api.make_appstorrent_resolver

    _pixeldrain_file_id = _api._pixeldrain_file_id
    _pixeldrain_file_info = _api._pixeldrain_file_info
    _pixeldrain_direct_url = _api._pixeldrain_direct_url
    _resolve_pixeldrain_download_url = _api._resolve_pixeldrain_download_url
    pixeldrain_resolved_metadata = _api.pixeldrain_resolved_metadata
    PIXELDRAIN_BYPASS_HOSTS = tuple(_api.PIXELDRAIN_BYPASS_HOSTS)

    torbox = _torbox

except Exception as exc:  # sin resolver_pack: stubs funcionales
    HAS_RESOLVER_PACK = False
    logger.debug("resolver_pack no presente (%s); usando stubs.", exc)

    # Soporte público de Pixeldrain: aunque no exista resolver_pack, los
    # links de Pixeldrain de la hoja se resuelven (bypass o API directa).
    # Sin esto el engine bajaría la página HTML de vista y fallaría.
    from services.pixeldrain_helpers import (   # noqa: F401
        _pixeldrain_file_id,
        _pixeldrain_file_info,
        _pixeldrain_direct_url,
        _resolve_pixeldrain_download_url,
        pixeldrain_resolved_metadata,
        PIXELDRAIN_BYPASS_HOSTS,
    )

    def _resolve_download_link(app: str) -> tuple:
        """Sin el pack privado no hay links configurados → método manual."""
        return "manual", ""

    URL_RESOLVERS: list = []

    def _no(url: str, *args, **kwargs) -> bool:
        return False

    is_akirabox_url = _no
    is_appstorrent_url = _no
    is_swisstransfer_url = _no
    is_workupload_url = _no
    is_pixeldrain_url = _no
    is_seyarabata_url = _no

    def _no_factory(link, *args, **kwargs):
        def resolve() -> tuple[str, dict[str, str]]:
            raise RuntimeError("resolver_pack no disponible en este entorno")
        return resolve

    make_akirabox_resolver = _no_factory
    make_swisstransfer_resolver = _no_factory
    make_seyarabata_resolver = _no_factory
    make_appstorrent_resolver = _no_factory

    def make_pixeldrain_resolver(link, app=None, **kwargs):
        """Resolver público de Pixeldrain: convierte /u/<id> en /api/file/<id>.
        No requiere resolver_pack; el bypass/API lo maneja el engine."""
        def resolve() -> tuple[str, dict[str, str]]:
            return _pixeldrain_direct_url(link), {}
        return resolve

    def _no_pixeldrain(url: str) -> str:
        return url

    def _no_pixeldrain_tuple(url: str) -> tuple:
        return None, 0, False, ""

    # Los helpers públicos de Pixeldrain (importados arriba) resuelven
    # /u/<id> y /api/file/<id> sin el pack privado; no se sobreescriben.

    class TorrentDownloader:
        """Stub: sin el pack privado no hay clientes torrent."""

        def __init__(self, *args, **kwargs):
            pass

    torbox = None


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


def has_resolver(kind: str) -> bool:
    """True si `kind` es un resolver conocido y está disponible.

    Pixeldrain es soporte PÚBLICO (nativo en services/pixeldrain_helpers.py),
    por lo que también está disponible sin el pack privado. El resto de
    kinks requiere resolver_pack.
    """
    if kind == "pixeldrain":
        return True
    if not HAS_RESOLVER_PACK:
        return False
    return kind in RESOLVER_KINDS


def get_resolver(kind: str, link: str, app: str = None, **kwargs):
    """Devuelve un resolver_callback para `kind` (activación lazy por app).

    Solo crea el callback del resolver pedido; no se instancia ningún otro.
    Pixeldrain usa el soporte público (sin pack). Sin el pack privado (o con
    un kind desconocido) lanza un error claro.
    """
    if kind == "pixeldrain":
        kwargs.setdefault("link", link)
        if app is not None:
            kwargs.setdefault("app", app)
        return make_pixeldrain_resolver(**kwargs)
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