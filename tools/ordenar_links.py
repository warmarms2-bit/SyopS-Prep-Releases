#!/usr/bin/env python3
"""Ordena la hoja Links: fusiona filas y genera un CSV limpio para pegar.

Modelo: una app se repite en varias filas SI cada método tiene su propio
link (matriz por método). Cuando varias filas del MISMO `(nombre, plataforma)`
comparten la MISMA `(url, resolver)` son intercambiables: se reducen a UNA fila
con `metodo` vacío (el servidor la acepta para cualquier método). Así se ordena
la hoja sin perder links y sin romper macheos.

Lectura de seguridad:
  - Clave de vendedor SOLO desde SYOPS_SELLER_KEY (env) o ~/.syops_seller_key.
    Nunca se imprime ni se guarda.
  - El CSV sale con las mismas columnas que getLinkHeaders() (incluye kind,
    que queda vacío para que llenes `tool` después).

Uso:
  python tools/ordenar_links.py                 # análisis + CSV en dry-run
  python tools/ordenar_links.py --out links_limpio.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

# ── Categorías del catálogo (APP_CATEGORY + OFFICE_APPS/CORE) ────────
try:
    from catalog.data import APP_CATEGORY as _APP_CAT
    from catalog.data import OFFICE_APPS as _OFFICE
    from catalog.data import OFFICE_CORE_APPS as _OFFICE_CORE
except ImportError:
    _APP_CAT, _OFFICE, _OFFICE_CORE = {}, frozenset(), []

_APP_CATEGORY: dict[str, str] = {n.strip(): c.strip() for n, c in _APP_CAT.items()}
for _n in list(_OFFICE) + list(_OFFICE_CORE):
    _APP_CATEGORY[_n.strip()] = "office"

# ── Casos especiales que no están en APP_CATEGORY ────────────────────
_SPECIAL_CAT = {
    "Maxon License": "graphic_design",
    "Mole": "optimization",
}

HEADERS = ["nombre", "metodo", "plataforma", "url", "resolver",
           "categoria", "categoria_seleccion", "kind", "apps_destino",
           "metodos"]

_SERVER = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
           or os.environ.get("SYOPS_SELLER_URL", "").strip()
           or "https://script.google.com/macros/s/AKfycbw6UrjoZCtUWyb2BxQskruTQRowGIv2dXuoHrupio1-UFN7ZLq-KIctzHjZCv0ikcSo/exec").strip()

_UA = {"User-Agent": "SyopsWizard-tools/1.3"}


def _seller_key() -> str:
    env = os.environ.get("SYOPS_SELLER_KEY", "").strip()
    if env:
        return env
    f = Path.home() / ".syops_seller_key"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "Falta la clave de vendedor. Configurala con:\n"
        "  export SYOPS_SELLER_KEY='tu-clave'   (o guardala en ~/.syops_seller_key)\n"
        "La agregáste en Apps Script > Configuración > Script Properties > SYOPS_SELLER_KEY."
    )


def fetch_links(server: str, key: str, timeout: float = 60) -> list:
    sep = "&" if "?" in server else "?"
    url = f"{server}{sep}action=get_links_seller&key={urllib.parse.quote(key)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(10000000).decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("status") != "ok":
        raise SystemExit(f"Respuesta inválida: {raw[:200]}")
    links = data.get("links")
    if not isinstance(links, list):
        raise SystemExit("Sin campo links en la respuesta")
    return links


def _clean(value) -> str:
    return str(value or "").strip()


def ordenar(links: list) -> tuple:
    """Reducción de filas. Devuelve (filas_ordenadas, resumen).

    Regla por grupo (nombre, plataforma):
      - Un solo (url, resolver) distinto → las filas son intercambiables:
        quedan UNA fila con `metodo` vacío (sirve a cualquier método).
      - Varios combos distintos → una fila por combo; cada fila conserva su
        método (si el combo trae una fila con metodo vacío, esa es la elegida).
    """
    resumen = {"antes": len(links), "despues": 0,
               "grupos": 0, "sin_url": 0, "win_descartados": 0}

    # Estado actual de la hoja:
    #  * Los links alojados en pixeldrain son SOLO de macos hoy.
    #  * Las herramientas (categoria == "Herramienta") como Sentinel, AntiCC,
    #    patchers, ACC Runtime, etc. son mac-only.
    #  * Algunas filas `win` son copias del archivo mac (misma URL para el
    #    mismo nombre). DaVinci/Raw swisstransfer, Blender DMG, etc. no son
    #    apps de windows reales. Si el `win` comparte URL con el `mac`, no es
    #    una cobertura adicional -> se descarta (un win legítimo usará su propia
    #    URL: magnet, github windows/ o sitio propio).
    mac_urls = {
        (_clean(r.get("nombre")), _clean(r.get("url")))
        for r in links
        if isinstance(r, dict)
        and _clean(r.get("nombre"))
        and _clean(r.get("url"))
        and _clean(r.get("plataforma") or "").lower() == "mac"
    }
    mac_names = {
        _clean(r.get("nombre")) for r in links
        if isinstance(r, dict)
        and _clean(r.get("nombre"))
        and _clean(r.get("plataforma") or "").lower() == "mac"
    }

    # Hosts de respaldo usados para subir la copia mac (swisstransfer,
    # akirabox, seyarabata). Un `win` cuyo archivo vive en uno de estos hosts
    # y que tiene gemelo `mac` es un backup mac mal etiquetado -> copia
    # espuria (ej. DaVinci Resolve). Apps de windows reales usan magnet,
    # descargas propias (download.blender.org, github/x o henrypp) o CDN
    # especificos.
    BACKUP_HOSTS = {"www.swisstransfer.com", "swisstransfer.com",
                    "akirabox.com", "seyarabata.com"}

    def _host(u: str) -> str:
        return u.lower().split("/")[2] if u.lower().startswith("https://") else ""

    grupos: dict = defaultdict(lambda: defaultdict(list))
    for item in links:
        if not isinstance(item, dict):
            continue
        nombre = _clean(item.get("nombre"))
        url = _clean(item.get("url"))
        if not nombre:
            continue
        if not url:
            resumen["sin_url"] += 1
            continue
        plataforma = _clean(item.get("plataforma")).lower()
        categoria = _clean(item.get("categoria")).lower()
        if plataforma == "win" and (
                url.lower().startswith("https://pixeldrain.com/")
                or categoria == "herramientas"
                or (nombre, url) in mac_urls
                or (_host(url) in BACKUP_HOSTS and nombre in mac_names)):
            resumen["win_descartados"] += 1
            continue
        combo = (url, _clean(item.get("resolver")))
        grupos[(nombre, plataforma)][combo].append(item)

    out = []
    for (nombre, plataforma), combos in grupos.items():
        unico = len(combos) == 1
        if not unico:
            resumen["grupos"] += 1
        for combo, filas in combos.items():
            vacia = [r for r in filas if not _clean(r.get("metodo"))]
            rep = vacia[0] if vacia else filas[0]
            row = dict(rep)
            if unico or vacia:
                row["metodo"] = ""
            else:
                row["metodo"] = _clean(rep.get("metodo"))
            row["plataforma"] = plataforma
            out.append(row)

    dedup, seen = [], set()
    for r in out:
        k = (r["nombre"], r["metodo"], r["plataforma"], r["url"], r["resolver"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    resumen["despues"] = len(dedup)
    dedup.sort(key=lambda r: (r["plataforma"], r["nombre"], r["metodo"]))

    # ── Auto-fill: kind=tool para Herramientas + Office helpers,
    #    categoria_seleccion desde APP_CATEGORY,
    #    apps_destino desde APP_TOOLS (reverso),
    #    metodos desde ADOBE_TOOLS.for_methods ─────────────────────
    try:
        from catalog.tools import APP_TOOLS as _ATOOLS
    except ImportError:
        _ATOOLS = {}
    _tool_to_apps: dict[str, list[str]] = {}
    for _app, _tools in _ATOOLS.items():
        for _t in _tools:
            _tool_to_apps.setdefault(_t.get("name", ""), []).append(_app)

    try:
        from catalog.adobe import ADOBE_TOOLS as _ADOBE_TOOLS
    except ImportError:
        _ADOBE_TOOLS = {}

    OFFICE_TOOLS = {"Microsoft AutoUpdate (MAU)",
                    "Microsoft Office LTSC 2024 VL Serializer"}
    for r in dedup:
        nombre = _clean(r.get("nombre"))
        cat = _clean(r.get("categoria")).lower()
        if cat == "herramientas" or nombre in OFFICE_TOOLS:
            r["kind"] = "tool"
            r["categoria_seleccion"] = ""
            # Auto-fill apps_destino para tools conocidas
            if not _clean(r.get("apps_destino")):
                apps = _tool_to_apps.get(nombre, [])
                if nombre in OFFICE_TOOLS:
                    try:
                        from catalog.categorias import OFFICE_APPS
                        apps = list(OFFICE_APPS)
                    except ImportError:
                        pass
                r["apps_destino"] = ", ".join(apps) if apps else ""
            # Auto-fill metodos desde ADOBE_TOOLS para tools Adobe
            if not _clean(r.get("metodos")) and nombre in _ADOBE_TOOLS:
                methods = _ADOBE_TOOLS[nombre].get("for_methods", [])
                r["metodos"] = ", ".join(methods) if methods else ""
        else:
            sel = _clean(r.get("categoria_seleccion"))
            if not sel:
                sel = _APP_CATEGORY.get(nombre, _SPECIAL_CAT.get(nombre, ""))
            r["categoria_seleccion"] = sel

    return dedup, resumen


def write_csv(rows: list, out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADERS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({h: _clean(r.get(h)) for h in HEADERS})
    print(f"  CSV escrito: {out} ({len(rows)} filas).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ordena la hoja Links -> CSV limpio.")
    ap.add_argument("--out", default="links_ordenado.csv")
    ap.add_argument("--server", default=_SERVER)
    ap.add_argument("--key", default="")
    args = ap.parse_args()

    key = (args.key or "").strip() or _seller_key()
    print("  Leyendo catálogo con get_links_seller...")
    links = fetch_links(args.server, key)
    print(f"  Filas en la hoja: {len(links)}")

    rows, resumen = ordenar(links)
    print("\n  RESUMEN")
    print(f"    antes        : {resumen['antes']}")
    print(f"    sin url      : {resumen['sin_url']}")
    print(f"    grupos c/url unica fusionados: {resumen['grupos']}")
    print(f"    win herramienta/pixeldrain descartados: {resumen['win_descartados']}")
    print(f"    despues      : {resumen['despues']}")

    write_csv(rows, args.out)
    print("\n  IMPORTANTE: pegá SOLO los datos (fila 2 en adelante, sin cabecera)\n"
          "  sobre la hoja Links confirmando el orden de columnas.\n"
          "  kind=tool y categoria_seleccion se autollenan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())