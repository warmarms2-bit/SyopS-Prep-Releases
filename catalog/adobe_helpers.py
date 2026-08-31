import platform
from catalog.data import (
    ADOBE_AIO_MACKED_LINKS, ADOBE_AIO_SICE_LINKS, ADOBE_MULTILANG_LINKS,
    ADOBE_FULL_PACK_COLLECTION, ADOBE_FULL_PACK_APPS, ADOBE_APPS,
    ADOBE_METHODS, ADOBE_TOOLS, ADOBE_APPS_PER_CREDIT,
)

def _get_mac_arch() -> str:
    """Detecta si el Mac es ARM (Apple Silicon) o Intel."""
    try:
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return "arm"
        if machine in ("x86_64", "amd64", "i386"):
            return "intel"
    except Exception:
        pass
    return "arm"  # default conservador para Macs recientes


# ── Compatibilidad con la estructura de links ────────────────────
# Formato actual de cada app en los dicts:
#   {"arm": {"url": str, "resolver": str}, "intel": {...}}   (antiguo: {"arm": url})
# Cada dict de links puede tener además ADOBE_FULL_PACK_COLLECTION en formato plano.
# Estas funciones normalizan las dos formas (string plana o dict anidado).

def _adobe_link_flat(entry, arch: str) -> str:
    """Retorna la URL string de una entrada de link (dict anidado o string plana)."""
    if entry is None:
        return ""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        arch_entry = entry.get(arch) or entry.get("arm") or entry.get("intel")
        if isinstance(arch_entry, dict):
            return arch_entry.get("url") or ""
        if isinstance(arch_entry, str):
            return arch_entry
    return ""


def _adobe_version(entry, arch: str) -> str:
    """Retorna la versión de una entrada de link (o '' si no tiene).

    La versión vive en el nivel superior del item de versión:
    {"version": "30.2.1", "arm": {"url":...}, "intel": {...}}.
    También acepta el caso {arch: {"url":..., "version":...}}.
    """
    if not isinstance(entry, dict):
        return ""
    if isinstance(entry.get("version"), str) and entry.get("version"):
        return entry["version"]
    arch_entry = entry.get(arch) or entry.get("arm") or entry.get("intel")
    if isinstance(arch_entry, dict):
        return arch_entry.get("version", "") or ""
    return ""


def _adobe_arch_link(source: dict, app: str, arch: str) -> tuple:
    """Retorna (url, version) para la app+arch en un source de links."""
    entry = source.get(app)
    if entry is None:
        return "", ""
    # Formato plano antiguo: {arm: url, intel: url}
    if isinstance(entry, dict) and not isinstance(entry.get("arm"), (dict,)) and \
            isinstance(entry.get(arch), str):
        return entry.get(arch) or "", ""
    return _adobe_link_flat(entry, arch), _adobe_version(entry, arch)


def _adobe_versions_for_app(method: str, app: str) -> list:
    """Devuelve la lista de versiones de la app en el método (más nueva primero).
    Cada ítem: {"version": str, "arm": {"url","resolver"}, "intel": {...}}.
    """
    source = _adobe_method_sources(method)
    entry = source.get(app)
    if isinstance(entry, list):
        return entry
    if isinstance(entry, dict) and "version" in str(entry.get("arm", "")):
        return [entry]
    if isinstance(entry, dict):
        return [entry]
    return []


def _adobe_versions_list(method: str, app: str) -> list:
    """Alias: lista de versiones de la app en el método (para UI/reportes)."""
    return _adobe_versions_for_app(method, app)


def _adobe_version_count(method: str, app: str) -> int:
    """Cantidad de versiones de la app disponibles en el método."""
    return len(_adobe_versions_for_app(method, app))


def _adobe_best_link(method: str, app: str, arch: str = None) -> tuple:
    """Elige la mejor (url, version) para descargar.

    Recorre las versiones de la app en el método (de más nueva a más vieja)
    y devuelve la primera cuyo link esté VIVO según link_health. Si ninguna
    está verificada, devuelve la más nueva (fallback). arch por defecto = el del Mac.
    """
    from services.link_health import is_url_known_dead
    if arch is None:
        arch = _get_mac_arch()
    versions = _adobe_versions_for_app(method, app)
    if not versions:
        return "", ""
    for v in versions:
        url = _adobe_link_flat(v, arch)
        if url and not is_url_known_dead(url):
            return url, v.get("version", "") if isinstance(v, dict) else ""
    # Fallback: primera versión
    first = versions[0]
    return _adobe_link_flat(first, arch), (first.get("version", "") if isinstance(first, dict) else "")


def _adobe_download_links_for_apps(apps: list, method: str) -> list:
    """
    Devuelve lista de (nombre, url) para descargar las apps Adobe elegidas
    usando el método y la arquitectura del Mac actual. Usa la mejor versión
    viva de cada app (link_health).
    """
    arch = _get_mac_arch()
    result = []
    if method == "aio_macked":
        source = ADOBE_AIO_MACKED_LINKS
    elif method == "aio_sice":
        source = ADOBE_AIO_SICE_LINKS
    elif method == "multilang_sice":
        source = ADOBE_MULTILANG_LINKS
    elif method == "activation_tool":
        # Activation Tool no descarga apps individuales; usa Adobe Downloader.
        return []
    else:
        return []
    for app in apps:
        if app not in source:
            continue
        url, _version = _adobe_best_link(method, app, arch)
        if url:
            result.append((app, url))
    return result


def _adobe_tools_for_method(method: str, sheet_items: list = None) -> list:
    """Devuelve lista de (nombre, url) de tools necesarios para el método.

    Lee de ``sheet_items`` (del get_tools_map). Filtra por método usando
    la columna ``metodos`` de la hoja. Si no hay items, devuelve [].
    """
    if not sheet_items:
        return []

    try:
        from catalog.tools import sheet_tool_metodos
    except ImportError:
        sheet_tool_metodos = None

    # Indexar sheet_items por nombre para acceso rápido
    sheet_by_name = {}
    for item in sheet_items:
        n = (item.get("name") or item.get("nombre") or "").strip()
        if n:
            sheet_by_name[n] = item

    result = []
    for name, cfg in ADOBE_TOOLS.items():
        sheet_item = sheet_by_name.get(name)
        if sheet_tool_metodos is not None and sheet_item:
            methods = sheet_tool_metodos(sheet_items, name)
            if methods:
                if method not in methods:
                    continue
        else:
            continue
        url = (sheet_item.get("url") or "").strip() if sheet_item else ""
        if not url:
            url = cfg.get("url", "")
        result.append((name, url))
    return result


def _adobe_method_sources(method: str) -> dict:
    """Devuelve el diccionario de links (app -> {arm, intel}) para el método Adobe."""
    if method == "aio_macked":
        return ADOBE_AIO_MACKED_LINKS
    if method == "aio_sice":
        return ADOBE_AIO_SICE_LINKS
    if method == "multilang_sice":
        return ADOBE_MULTILANG_LINKS
    return {}


def _adobe_apps_supported_by_method(method: str) -> set:
    """Devuelve el conjunto de apps Adobe soportadas por un método."""
    if method == "activation_tool":
        return set(ADOBE_APPS)
    return set(_adobe_method_sources(method).keys())


def _adobe_methods_for_app(app: str) -> list:
    """Devuelve lista de métodos Adobe que soportan la app dada."""
    methods = []
    for method in ADOBE_METHODS.keys():
        if app in _adobe_apps_supported_by_method(method):
            methods.append(method)
    return methods


def _adobe_full_pack_links(method: str) -> list:
    """Devuelve lista de (nombre, url) para descargar el Full Pack."""
    if method == "aio_macked":
        arch = _get_mac_arch()
        url = _adobe_link_flat(ADOBE_FULL_PACK_COLLECTION, arch)
        return [(ADOBE_FULL_PACK_COLLECTION["name"], url)] if url else []
    if method == "aio_sice":
        # Full Pack Sice no tiene un AIO collection; fallback a descargas individuales.
        return _adobe_download_links_for_apps(ADOBE_FULL_PACK_APPS, "aio_sice")
    if method == "multilang_sice":
        return _adobe_download_links_for_apps(ADOBE_FULL_PACK_APPS, "multilang_sice")
    if method == "activation_tool":
        return []
    return []


def _adobe_count_for_limit(apps: list) -> int:
    """
    Cuenta cuántas apps del límite total representan las apps de Adobe elegidas.
    Hasta ADOBE_APPS_PER_CREDIT apps de Adobe cuentan como 1.
    """
    adobe = [a for a in apps if a in ADOBE_APPS]
    if not adobe:
        return 0
    return max(1, (len(adobe) + ADOBE_APPS_PER_CREDIT - 1) // ADOBE_APPS_PER_CREDIT)


def _adobe_apps_in_selection(apps: list) -> list:
    """Devuelve solo las apps de Adobe presentes en la selección."""
    return [a for a in apps if a in ADOBE_APPS]
def _adobe_has_mac_link(app: str) -> bool:
    """Devuelve True si la app Adobe tiene al menos un link en algún dict de macOS."""
    for d in (ADOBE_AIO_MACKED_LINKS, ADOBE_AIO_SICE_LINKS, ADOBE_MULTILANG_LINKS):
        entry = d.get(app)
        if entry is None:
            continue
        if isinstance(entry, list):
            if any(_adobe_link_flat(v, "arm") or _adobe_link_flat(v, "intel") for v in entry):
                return True
        elif isinstance(entry, dict):
            if any(v for v in entry.values()):
                return True
        elif entry:
            return True
    return False
