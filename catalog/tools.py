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


def _app_tools_for_app(app: str) -> list:
    """Devuelve la lista de tools que acompañan a la app (consolida fuentes).

    Fuentes de tools por app:
      1. APP_TOOLS        — registro manual declarativo (fuente principal)
      2. ADOBE_PATCHERS_SICE — patcher por app Adobe (Photoshop, Illustrator...)
      3. OFFICE_CORE_APPS — components core que acompañan a Office (MAU, Serializer)
      4. ADOBE_TOOLS      — tools del método Adobe que aplican a esa app

    Cada ítem: {name, url, doc?, required?, source}
    """
    tools = list(APP_TOOLS.get(app, []))

    try:
        from catalog.adobe import ADOBE_APPS
    except Exception:
        ADOBE_APPS = frozenset()

    if app in ADOBE_APPS:
        try:
            from catalog.adobe import ADOBE_PATCHERS_SICE, ADOBE_TOOLS
        except Exception:
            ADOBE_PATCHERS_SICE, ADOBE_TOOLS = {}, {}
        if app in ADOBE_PATCHERS_SICE:
            tools.append({
                "name": f"{app} Patcher",
                "url": ADOBE_PATCHERS_SICE[app],
                "source": "adobe_patcher",
                "required": True,
            })
        # Sentinel es tool común de todos los métodos Adobe.
        if "Sentinel" in ADOBE_TOOLS:
            cfg = ADOBE_TOOLS["Sentinel"]
            tools.append({
                "name": "Sentinel",
                "url": cfg["url"],
                "doc": "",
                "source": "adobe_method_tool",
                "required": cfg.get("required", True),
            })

    if app == "Office":
        try:
            from catalog.categorias import OFFICE_CORE_APPS
            from catalog.urls import _DOWNLOAD_URLS_MAC
        except Exception:
            OFFICE_CORE_APPS, _DOWNLOAD_URLS_MAC = [], {}
        for core in OFFICE_CORE_APPS:
            url = _DOWNLOAD_URLS_MAC.get(core, "")
            tools.append({
                "name": core,
                "url": url,
                "source": "office_core",
                "required": True,
            })

    # Sub-apps de Office (Word, Excel...) heredan las tools de Office.
    try:
        from catalog.categorias import OFFICE_CORE_APPS, OFFICE_APPS
        from catalog.urls import _DOWNLOAD_URLS_MAC
        if app in OFFICE_APPS:
            for core in OFFICE_CORE_APPS:
                url = _DOWNLOAD_URLS_MAC.get(core, "")
                if url and not any(t.get("name") == core for t in tools):
                    tools.append({
                        "name": core,
                        "url": url,
                        "source": "office_core",
                        "required": True,
                    })
    except Exception:
        pass

    return tools


def _all_app_tools() -> list:
    """Devuelve lista plana de todas las tools registradas (con 'app').
    Incluye las fuentes consolidadas: APP_TOOLS, patchers Adobe, Office core.
    """
    result = []
    for app in _apps_with_tools():
        for t in _app_tools_for_app(app):
            result.append(dict(t, app=app))
    return result


def _apps_with_tools() -> set:
    """Set de apps que tienen al menos una tool registrada (cualquier fuente)."""
    apps = set(APP_TOOLS.keys())
    try:
        from catalog.adobe import ADOBE_PATCHERS_SICE, ADOBE_APPS
        apps.update(ADOBE_PATCHERS_SICE.keys())
        # Todos los Adobe usan al menos Sentinel como tool del método.
        apps.update(ADOBE_APPS)
    except Exception:
        pass
    apps.add("Office")
    try:
        from catalog.categorias import OFFICE_APPS
        apps.update(OFFICE_APPS)  # Word, Excel, PowerPoint... heredan tools
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
