from i18n import _

COMBO_TOOLS = {
    "Mole + Talon": ["Mole", "Talon"],
}


TOOL_APPS = {"Mole + Talon", "SimpleWall"}


# ── TOOLS POR APP ──────────────────────────────────────────────────
# Registro de herramientas que acompañan a una app específica cuando se
# descarga. Cada entrada:
#   "App objetivo": [
#       {
#           "name": "Nombre tool",
#           "url":  "",          # link de descarga de la tool
#           "doc":  "",          # documentación (opcional)
#           "required": True,               # obligatoria para la app
#       },
#   ]
# La tool se descarga junto a la app objetivo y se muestra en el resumen.
# Para agregar: sumar una entrada en APP_TOOLS y opcionalmente una
# descripción en TOOL_DESCS.
APP_TOOLS = {
    "SketchUp Pro": [
        {
            "name": "SketchUp Patcher 2026",
            "url": "",
            "doc": "",
            "required": True,
        },
    ],
    "Archicad": [
        {
            "name": "Archicad 29.2.1 Patcher ARM",
            "url": "",
            "doc": "",
            "required": True,
        },
    ],
    "DaVinci Resolve": [
        {
            "name": "DaVinci Resolve Flickering Fix",
            "url": "",
            "doc": "",
            "required": False,
        },
    ],
}

# Tool compartida de Steinberg (patcher de licencias) usada por varias apps.
_STEINBERG_PATCHER = {
    "name": "Steinberg Patcher",
    "url": "",
    "doc": "",
    "required": True,
}

# Apps Steinberg que usan el patcher compartido.
for _steinberg_app in ("Cubase Pro", "Nuendo", "Dorico Pro", "WaveLab Pro",
                       "GrooveAgent", "VST Live Pro", "SpectraLayers Pro"):
    APP_TOOLS.setdefault(_steinberg_app, []).append(dict(_STEINBERG_PATCHER))
del _steinberg_app


def _app_tools_for_app(app: str, sheet_items: list = None) -> list:
    """Devuelve la lista de tools que acompañan a la app.

    Lee de ``sheet_items`` (lista de dicts de la hoja Links).
    Si no hay items, devuelve lista vacía.

    Cada ítem: {name, url, doc?, required?, source}
    """
    if not sheet_items:
        return []
    return _tools_from_sheet(app, sheet_items)


def _tools_from_sheet(app: str, items: list) -> list:
    """Arma tools para ``app`` desde la hoja Links (columna apps_destino).

    Lee cada fila (todas son kind=tool porque get_tools_map ya filtra),
    parsea ``apps_destino`` (comma-separated) y si ``app`` está en esa
    lista, agrega la tool al resultado.
    """
    import re
    tools = []
    for row in items:
        if not isinstance(row, dict):
            continue
        destino_raw = (row.get("apps_destino") or "").strip()
        if not destino_raw:
            continue
        destinos = {d.strip().casefold() for d in re.split(r",\s*", destino_raw) if d.strip()}
        if app.casefold() in destinos:
            metodos_raw = (row.get("metodos") or "").strip()
            tools.append({
                "name": (row.get("name") or row.get("nombre") or "").strip(),
                "url": (row.get("url") or "").strip(),
                "doc": "",
                "required": True,
                "source": "sheet",
                "metodos": metodos_raw,
            })
    return tools


def sheet_tool_metodos(sheet_items: list, tool_name: str) -> list:
    """Devuelve la lista de métodos de una tool desde la hoja.

    Busca en ``metodo_destinos`` primero, fallback a ``metodos``.
    Si la tool no está en la hoja o el campo está vacío, devuelve [].
    """
    import re
    for row in sheet_items:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or row.get("nombre") or "").strip()
        if name != tool_name:
            continue
        metodos_raw = (row.get("metodos") or "").strip()
        if not metodos_raw:
            return []
        return [m.strip() for m in re.split(r",\s*", metodos_raw) if m.strip()]
    return []


def _all_app_tools(sheet_items: list = None) -> list:
    """Devuelve lista plana de todas las tools registradas (con 'app')."""
    result = []
    for app in _apps_with_tools(sheet_items):
        for t in _app_tools_for_app(app, sheet_items):
            result.append(dict(t, app=app))
    return result


def _apps_with_tools(sheet_items: list = None) -> set:
    """Set de apps que tienen al menos una tool registrada.

    Con ``sheet_items`` usa la hoja como fuente; sin ella, el hardcode local.
    """
    if sheet_items is not None:
        import re
        apps = set()
        for row in sheet_items:
            if not isinstance(row, dict):
                continue
            destino_raw = (row.get("apps_destino") or "").strip()
            if not destino_raw:
                continue
            for d in re.split(r",\s*", destino_raw):
                d = d.strip()
                if d:
                    apps.add(d)
        return apps

    apps = set(APP_TOOLS.keys())
    try:
        from catalog.adobe import ADOBE_PATCHERS_SICE, ADOBE_APPS
        apps.update(ADOBE_PATCHERS_SICE.keys())
        apps.update(ADOBE_APPS)
    except Exception:
        pass
    apps.add("Office")
    try:
        from catalog.categorias import OFFICE_APPS
        apps.update(OFFICE_APPS)
    except Exception:
        pass
    return apps


def _expand_apps(apps):
    expanded = []
    for a in apps:
        if a in COMBO_TOOLS:
            expanded.extend(COMBO_TOOLS[a])
        else:
            expanded.append(a)
    return expanded


TOOL_DESCS = {
    "Mole + Talon": _("info.tool_mole"),
    "Mole": _("info.tool_mole_solo"),
    "Talon": _("info.tool_talon_solo"),
    "SimpleWall": _("info.tool_simplewall"),
}

# ── URLs DE DOCUMENTACIÓN DE TOOLS ─────────────────────────────────
# Cada tool define su URL de documentación junto a su definición.
# Las páginas UI la consumen desde aquí (no hardcodeada en la UI).
# Orden de precedencia: la tool es la fuente de verdad; la UI replica.
TOOL_DOC_URLS = {
    "Mole": "",
    "Talon": "",
    "SimpleWall": "",
}
