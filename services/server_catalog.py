"""Catálogo de categorías provisto por el servidor (hoja Links).

El wizard arma el árbol de categorías desde la hoja `Links` (columna
`categoria`, sin URLs) con fallback al catálogo local si el backend no
responde o no trae datos. Así el vendedor puede organizar grupos nuevos
escribiendo `categoria` en el sheet, y el programa sigue funcionando
offline con las categorías locales conocidas.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_OTRA = "Otra"

_UA = {"User-Agent": "SyopsWizard/1.3"}


def fetch_catalog_index(server_url: str, timeout: float = 6) -> list | None:
    """Consulta `get_catalog_index` y devuelve `[{nombre, plataforma, categoria}]`.

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


def _invert_local(local_categories: dict) -> tuple:
    """Dos mapas: app UPPER -> clave local, y clave local -> label_key."""
    by_app = {}
    labels = {}
    for key, info in local_categories.items():
        if key == "all":
            continue
        labels[key] = info.get("label_key", key)
        for app in info.get("apps", []):
            by_app[str(app).upper()] = key
    return by_app, labels


def build_catalog(items: list, os_key: str, local_categories: dict,
                  otra: str = DEFAULT_OTRA) -> dict | None:
    """Construye `{bucket: {"label": str|None, "label_key": str|None, "apps": []}}`.

    - Cada item con plataforma == os_key entra agrupado por su `categoria`.
    - Si algún item del bucket trae `categoria`, esa cadena es el label de
      pantalla; si ningún item la trae, se usa el label_key local de la app
      (caption i18n) para no romper categorías conocidas.
    - Devuelve None si no queda ningún item para este SO.
    """
    from collections import OrderedDict

    local_for, label_of = _invert_local(local_categories)
    cat: OrderedDict[str, dict] = OrderedDict()

    def bucket(item: dict) -> str:
        categoria = (item.get("categoria") or "").strip()
        if categoria:
            return categoria
        app_upper = (item.get("nombre") or "").strip().upper()
        return local_for.get(app_upper) or otra

    for item in items:
        if not isinstance(item, dict):
            continue
        plataforma = (item.get("plataforma") or "").strip().lower()
        if plataforma and plataforma != os_key:
            continue
        nombre = (item.get("nombre") or "").strip()
        if not nombre:
            continue
        key = bucket(item)
        entry = cat.setdefault(key, {"label": None, "label_key": None, "apps": []})
        categoria = (item.get("categoria") or "").strip()
        if categoria:
            entry["label"] = categoria
        elif entry["label_key"] is None:
            entry["label_key"] = label_of.get(key, key)
        if nombre not in entry["apps"]:
            entry["apps"].append(nombre)
    for entry in cat.values():
        if entry["label"] is None and entry["label_key"] is None:
            entry["label_key"] = otra
    if not cat:
        return None
    return dict(cat)