#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  DOWNLOAD RESOLVERS - Disponibilidad y formato de links.
#  Contiene SOLO lógica genérica del repo público. La resolución real
#  de links (know-how de hosts) vive en resolver_pack/ y se accede vía
#  services/resolver_gateway.py.
# ═══════════════════════════════════════════════════════════════════

import logging
from pathlib import Path

from catalog.data import (
    ADOBE_APPS, DOWNLOAD_METHODS, APP_CATEGORY, INSTALL_INSTRUCTIONS,
)
from services.resolver_gateway import _resolve_download_link

logger = logging.getLogger(__name__)


def _write_instructions_file(output_folder: Path, apps: list):
    """Genera instrucciones.txt en la carpeta de descargas."""
    if not output_folder:
        return
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for app in apps:
        steps = INSTALL_INSTRUCTIONS.get(app)
        if not steps:
            continue
        lines.append(f"=== {app} ===")
        for i, step in enumerate(steps, start=1):
            lines.append(f"{i}. {step}")
        lines.append("")
    if not lines:
        return
    content = "INSTRUCCIONES DE INSTALACIÓN\n" + "=" * 40 + "\n\n" + "\n".join(lines)
    try:
        (output_folder / "instrucciones.txt").write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning("No se pudo escribir el archivo de instrucciones: %s", e)


# ── DISPONIBILIDAD POR PLATAFORMA ────────────────────────────────

import os as _os
import time as _time

# Dict dinámico llenado desde el sheet (columna ``plataforma``).
# Se actualiza cuando el wizard carga el catálogo desde el servidor.
_sheet_platforms: dict[str, str] = {}
_sheet_last_refresh: float = 0.0
# Último intento de fetch (éxito o fallo): el cooldown aplica SIEMPRE, para
# que un backend caído no dispare una llamada de red por cada app consultada.
_sheet_last_attempt: float = 0.0
_REFRESH_INTERVAL = 300  # re-intentar cada 5 minutos si el sheet no cargó


def set_sheet_platforms(platforms: dict[str, str]):
    """Actualiza el dict de plataformas desde el sheet."""
    global _sheet_last_refresh
    _sheet_platforms.clear()
    _sheet_platforms.update(platforms)
    _sheet_last_refresh = _time.time()


def _try_refresh_sheet_platforms():
    """Re-intenta cargar platforms del sheet respetando el cooldown siempre.

    El reintento se espacia cada ``_REFRESH_INTERVAL`` segundos tanto si el
    intento anterior falló como si tuvo éxito: así importar el módulo o
    consultar muchas apps no genera una tormenta de peticiones de red.
    Además respeta ``SYOPS_NO_CATALOG_FETCH=1`` (modo offline/tests): nunca
    consulta el backend en ese modo.
    """
    global _sheet_last_attempt
    now = _time.time()
    if now - _sheet_last_attempt < _REFRESH_INTERVAL:
        return
    _sheet_last_attempt = now
    if _sheet_platforms and (now - _sheet_last_refresh) < _REFRESH_INTERVAL:
        return
    if _os.environ.get("SYOPS_NO_CATALOG_FETCH", "") in ("1", "true", "True"):
        return
    try:
        from app_config import LINK_SERVER_URL
        from catalog.base import IS_MAC
        from services.server_catalog import fetch_catalog_index, build_catalog
        from catalog.data import SOFTWARE_CATEGORIES
        import os
        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            return
        items = fetch_catalog_index(server, timeout=4)
        if not items:
            return
        os_key = "mac" if IS_MAC else "win"
        _, _, platforms = build_catalog(items, os_key, SOFTWARE_CATEGORIES)
        if platforms:
            set_sheet_platforms(platforms)
    except Exception:
        pass


def _has_real_url(d: dict, key: str) -> bool:
    val = d.get(key, "")
    return bool(val) and val != "combo"


def _is_app_available_on_platform(app: str, platform: str) -> bool:
    """Devuelve True si la app está disponible para esa plataforma.

    Usa la columna 'plataforma' del sheet cuando está disponible.
    Si el sheet no cargó, cae a la tabla estática de compatibilidad
    (catalog/plataformas.py), que replica el filtro del catálogo original
    sin URLs. Solo si la app no está en esa tabla se muestra (default
    conservador para apps agregadas después).
    """
    _try_refresh_sheet_platforms()
    if _sheet_platforms:
        plat = _sheet_platforms.get(app, "")
        if not plat:
            return False
        if plat == "none":
            return False
        if platform == "mac":
            return plat in ("mac", "both")
        return plat in ("win", "both")
    # Sheet no cargó: tabla estática de compatibilidad (sin red).
    from catalog.plataformas import is_compatible
    return is_compatible(app, platform)


# ── CONJUNTOS DE DISPONIBILIDAD POR PLATAFORMA ───────────────────
# Calculados automáticamente (no hardcodeados).
# Se usan para validate_links.py. En el futuro también para filtrar la UI.
#
# ⚠ Lazy por diseño: calcularlos a nivel de módulo disparaba una llamada de
# red al backend por cada app (importar el módulo podía tardar minutos o
# colgarse). Ahora se calculan en el primer uso y se cachean.

_ALL_KNOWN_APPS = (set(DOWNLOAD_METHODS.keys())
                   | set(APP_CATEGORY.keys())
                   | set(ADOBE_APPS))

_MAC_ONLY_CACHE: frozenset | None = None
_WIN_ONLY_CACHE: frozenset | None = None


def mac_only_apps() -> frozenset:
    """Apps disponibles solo en macOS (calculado en el primer uso)."""
    global _MAC_ONLY_CACHE
    if _MAC_ONLY_CACHE is None:
        _MAC_ONLY_CACHE = frozenset(
            a for a in _ALL_KNOWN_APPS
            if _is_app_available_on_platform(a, "mac")
            and not _is_app_available_on_platform(a, "win")
        )
    return _MAC_ONLY_CACHE


def win_only_apps() -> frozenset:
    """Apps disponibles solo en Windows (calculado en el primer uso)."""
    global _WIN_ONLY_CACHE
    if _WIN_ONLY_CACHE is None:
        _WIN_ONLY_CACHE = frozenset(
            a for a in _ALL_KNOWN_APPS
            if _is_app_available_on_platform(a, "win")
            and not _is_app_available_on_platform(a, "mac")
        )
    return _WIN_ONLY_CACHE


def _missing_download_links(apps: list) -> list:
    """Devuelve lista de apps que tienen método de descarga pero no tienen link configurado."""
    missing = []
    for app in apps:
        method, link = _resolve_download_link(app)
        if method in ("torrent", "http", "torbox") and not link:
            missing.append(app)
    return missing


def _validate_link_format(method: str, link: str) -> str | None:
    """Devuelve None si el formato del link coincide con el method,
    o un mensaje de error específico para mostrar en la UI si hay desajuste."""
    if not link:
        # Link vacío: problema de ausencia, no de formato (manejado aparte).
        return None
    if method == "torrent":
        if not link.startswith("magnet:"):
            display = link[:80] + "..." if len(link) > 80 else link
            return (
                f"Config error: method=torrent pero el link no es un magnet "
                f"(recibido: {display})"
            )
    elif method == "http":
        if link.startswith("magnet:"):
            display = link[:80] + "..." if len(link) > 80 else link
            return (
                f"Config error: method=http pero el link es un magnet "
                f"(recibido: {display})"
            )
        if not (link.startswith("http://") or link.startswith("https://")):
            display = link[:80] + "..." if len(link) > 80 else link
            return (
                f"Config error: method=http pero el link no usa http/https "
                f"(recibido: {display})"
            )
    elif method == "torbox":
        is_http = link.startswith("http://") or link.startswith("https://")
        is_magnet = link.startswith("magnet:")
        if not is_http and not is_magnet:
            display = link[:80] + "..." if len(link) > 80 else link
            return (
                f"Config error: method=torbox pero el link no es magnet "
                f"ni http/https (recibido: {display})"
            )
    return None