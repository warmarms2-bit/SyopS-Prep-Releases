"""Lógica pura de selección/descarga (sin UI).

Funciones de negocio extraídas de ui/main.py para reducir el tamaño
del orquestador y permitir testeo unitario aislado.
"""

import urllib.parse
from catalog.data import ADOBE_APPS, COMBO_TOOLS, DOWNLOAD_METHODS, OFFICE_PARENT, _expand_office_for_downloads
from catalog.categorias import OFFICE_APPS, OFFICE_CORE_APPS
from services.resolver_gateway import (
    _resolve_download_link,
    is_akirabox_url,
    is_swisstransfer_url,
    is_workupload_url,
    is_pixeldrain_url,
    is_seyarabata_url,
)


def describe_method(app: str, method: str = None) -> str:
    """Devuelve un nombre legible del método/resolver de una app.

    Para downloads HTTP genéricos, detecta el resolver real del link
    (Pixeldrain, AkiraBox, SwissTransfer, Workupload) en vez de solo 'http'.
    Devuelve la cadena raw para apps sin link directo.
    """
    if method not in (None, "http", "torrent"):
        return method
    try:
        resolved_method, link = _resolve_download_link(app)
    except Exception:
        return method or "manual"
    if not link:
        return method or "manual"
    # Detectar el resolver del link HTTP.
    if is_pixeldrain_url(link):
        return "pixeldrain"
    if is_akirabox_url(link):
        return "akirabox"
    if is_swisstransfer_url(link):
        return "swisstransfer"
    if is_workupload_url(link):
        return "workupload"
    if is_seyarabata_url(link):
        return "seyarabata"
    if resolved_method == "torrent":
        return "torrent"
    host = urllib.parse.urlparse(link).netloc
    return host if host else "http"


def build_download_apps(apps: list, office_sub_apps: list, adobe_patched: list,
                        sheet_methods: dict | None = None) -> list:
    """Construye la lista final de descargas incluyendo Office y Adobe."""
    raw_download_apps = _expand_office_for_downloads(apps, office_sub_apps)
    methods = sheet_methods or {}
    def _has_method(a):
        return methods.get(a) is not None or DOWNLOAD_METHODS.get(a) is not None
    download_apps = []
    for a in raw_download_apps:
        if a in COMBO_TOOLS:
            for sub in COMBO_TOOLS[a]:
                if _has_method(sub):
                    download_apps.append(sub)
        elif a in ADOBE_APPS:
            if a not in adobe_patched:
                download_apps.append(a)
        elif a == OFFICE_PARENT:
            continue
        else:
            if _has_method(a):
                download_apps.append(a)
    if any(a in ADOBE_APPS and a in adobe_patched for a in apps):
        download_apps.append("GenP")
    if any(a in OFFICE_APPS or a == OFFICE_PARENT for a in apps):
        for core in OFFICE_CORE_APPS:
            if core not in download_apps and _has_method(core):
                download_apps.append(core)
    if not download_apps:
        download_apps = [a for a in raw_download_apps if _has_method(a)]
    return download_apps


def has_downloadable(apps: list, activation_type: str, sheet_methods: dict | None = None) -> bool:
    """Determina si la selección requiere descargas."""
    if activation_type == "adobe_full_pack":
        return True
    if any(a in ADOBE_APPS for a in apps):
        return True
    methods = sheet_methods or DOWNLOAD_METHODS
    return any(methods.get(a) is not None or DOWNLOAD_METHODS.get(a) is not None for a in apps)


def effective_method_str(activation_type: str, adobe_method: str, sheets_method: str) -> str:
    """Devuelve el método a registrar en Sheets considerando Adobe."""
    if activation_type == "adobe_full_pack":
        return "adobe_full_pack"
    if adobe_method:
        return f"adobe_{adobe_method}"
    return sheets_method
