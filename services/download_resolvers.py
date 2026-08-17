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
    _DOWNLOAD_URLS_MAC, _DOWNLOAD_URLS_WIN, DOWNLOAD_URLS,
    _TORRENT_MAGNETS_MAC, _TORRENT_MAGNETS_WIN, TORRENT_MAGNETS,
    TORBOX_LINKS, SWISSTRANSFER_URLS,
)
from catalog.adobe_helpers import _adobe_has_mac_link
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

def _has_real_url(d: dict, key: str) -> bool:
    val = d.get(key, "")
    return bool(val) and val != "combo"


def _is_app_available_on_platform(app: str, platform: str) -> bool:
    """Devuelve True si la app estaba disponible para esa plataforma.

    Usa la tabla estática de compatibilidad (catalog/plataformas.py), que
    replica el filtro del catálogo original SIN exponer URLs de descarga
    en el cliente.
    """
    from catalog.plataformas import is_compatible
    return is_compatible(app, platform)


# ── CONJUNTOS DE DISPONIBILIDAD POR PLATAFORMA ───────────────────
# Calculados automáticamente (no hardcodeados).
# Se usan para validate_links.py. En el futuro también para filtrar la UI.

_ALL_KNOWN_APPS = (set(DOWNLOAD_METHODS.keys())
                   | set(APP_CATEGORY.keys())
                   | set(ADOBE_APPS))

MAC_ONLY_APPS = frozenset(
    a for a in _ALL_KNOWN_APPS
    if _is_app_available_on_platform(a, "mac")
    and not _is_app_available_on_platform(a, "win")
)

WIN_ONLY_APPS = frozenset(
    a for a in _ALL_KNOWN_APPS
    if _is_app_available_on_platform(a, "win")
    and not _is_app_available_on_platform(a, "mac")
)


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