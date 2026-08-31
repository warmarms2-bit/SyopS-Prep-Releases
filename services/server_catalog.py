"""Catálogo de categorías provisto por el servidor (hoja Links).

El wizard arma el árbol de categorías de selección desde la hoja `Links`
(columna `categoria_seleccion`). El label mostrado en pantalla es SIEMPRE
el valor de esa columna (o la key del bucket si no hay).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_OTRA = "Otra"

_UA = {"User-Agent": "SyopsWizard/1.3"}


def fetch_catalog_index(server_url: str, timeout: float = 6) -> list | None:
    """Consulta `get_catalog_index` y devuelve `[{nombre, plataforma,
    categoria, categoria_seleccion}]`.

    Devuelve None si el backend no responde o la respuesta no es válida
    (el llamador cae al catálogo local). Nunca lanza excepciones.
    """
    server = (server_url or "").strip()
    if not server:
        return None
    sep = "&" if "?" in server else "?"
    url = f"{server}{sep}action=get_catalog_index"
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200000).decode("utf-8", "replace")
        data = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("status") != "ok":
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    return items


def build_catalog(items: list, os_key: str, local_categories: dict = None,
                  otra: str = DEFAULT_OTRA) -> tuple[dict | None, dict, dict]:
    """Construye `{bucket: {"label": str, "apps": []}}` desde la hoja Links.

    Devuelve ``(catalog, methods, platforms)`` donde:
    - *catalog* es el árbol de categorías
    - *methods* es un dict ``{app_name: resolver_value}`` de la columna ``resolver``
    - *platforms* es un dict ``{app_name: plataforma}`` de la columna ``plataforma``

    - Cada item con plataforma == os_key entra agrupado por su
      `categoria_seleccion` (la columna de la hoja `Links`).
    - Las filas `kind == "tool"` se excluyen.
    - El label es SIEMPRE el valor de `categoria_seleccion` del sheet
      (o la key del bucket si no hay).
    - Devuelve (None, {}, {}) si no queda ningún item para este SO.
    """
    from collections import OrderedDict

    cat: OrderedDict[str, dict] = OrderedDict()
    methods: dict[str, str] = {}
    platforms: dict[str, str] = {}

    seen_names = {
        str(it.get("nombre") or "").strip().casefold()
        for it in items if isinstance(it, dict)
    }

    def group_valid(value: str) -> bool:
        v = (value or "").strip()
        if not v or "," in v:
            return False
        return v.casefold() not in seen_names

    def bucket(item: dict) -> str:
        seleccion = (item.get("categoria_seleccion") or "").strip()
        if group_valid(seleccion):
            return seleccion
        app_upper = (item.get("nombre") or "").strip().upper()
        # Fallback: usar nombre de la app como bucket (no traducción local)
        return app_upper or otra

    for item in items:
        if not isinstance(item, dict):
            continue
        if (item.get("kind") or "").strip().lower() == "tool":
            continue
        plataforma = (item.get("plataforma") or "").strip().lower()
        if plataforma and plataforma != os_key:
            continue
        nombre = (item.get("nombre") or "").strip()
        if not nombre:
            continue
        key = bucket(item)
        entry = cat.setdefault(key, {"label": None, "apps": []})
        seleccion = (item.get("categoria_seleccion") or "").strip()
        if group_valid(seleccion):
            entry["label"] = seleccion
        elif entry["label"] is None:
            # Sin categoria_seleccion: usar la key como label
            entry["label"] = key
        if nombre not in entry["apps"]:
            entry["apps"].append(nombre)
        resolver = (item.get("resolver") or "").strip()
        if resolver and nombre not in methods:
            methods[nombre] = resolver
        raw_plat = (item.get("plataforma") or "").strip().lower()
        if raw_plat and nombre not in platforms:
            platforms[nombre] = raw_plat
    for entry in cat.values():
        if entry["label"] is None:
            entry["label"] = otra
    if not cat:
        return None, methods, platforms
    return dict(cat), methods, platforms