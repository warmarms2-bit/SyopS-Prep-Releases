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

HEADERS = ["nombre", "metodo", "plataforma", "url", "resolver",
           "categoria", "categoria_seleccion", "kind"]

_SERVER = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
           or os.environ.get("SYOPS_SELLER_URL", "").strip()
           or "https://script.google.com/macros/s/AKfycbyti1-M-64wiN0NfAiuTv3QRz0-ZTmYhZLo22T7GmQdMa2DvRTU7qxcaMRrA-e30IS1/exec").strip()

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

    Resumen: {antes, despues, grupos_fusionados, filas_sin_url}.
    """
    out = []
    resumen = {"antes": len(links), "despues": 0,
               "grupos": 0, "sin_url": 0}

    # Agrupar por (nombre, plataforma), subgrupar por (url, resolver).
    grupos: dict = defaultdict(dict)
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
        combo = (_clean(item.get("url")), _clean(item.get("resolver")))
        key = (nombre, plataforma)
        grupos.setdefault(key, {})
        # Conservar el primer metodo="" si existe; si no, el primer metodo.
        bucket = grupos[key].setdefault(combo, {
            "row": None, "metodo": "",
        })
        metodo = _clean(item.get("metodo"))
        if bucket["row"] is None:
            bucket["row"] = item
            bucket["metodo"] = metodo
        elif not bucket["metodo"] and metodo:
            # Ya había vacío: no pisar. (Si el primero no fue vacío y éste sí,
            # preferimos vacío como universal.)
            if bucket["metodo"] != "":
                bucket["metodo"] = ""
                bucket["row"] = item
        if not bucket["metodo"]:
            bucket["metodo"] = ""

    for (nombre, plataforma), combos in grupos.items():
        if len(combos) > 1:
            resumen["grupos"] += 1
        for combo, bucket in combos.items():
            row = dict(bucket["row"])
            row["metodo"] = bucket["metodo"]
            out.append(row)

    resumen["despues"] = len(out)
    dedup = []
    seen = set()
    for r in out:
        k = (r["nombre"], r["metodo"], r["plataforma"], r["url"], r["resolver"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    resumen["despues"] = len(dedup)
    dedup.sort(key=lambda r: (r["plataforma"], r["nombre"], r["metodo"]))
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
    print(f"    despues      : {resumen['despues']}")

    write_csv(rows, args.out)
    print("\n  IMPORTANTE: pegá SOLO los datos (fila 2 en adelante, sin cabecera)\n"
          "  sobre la hoja Links confirmando el orden de columnas. Después\n"
          "  llenás `kind=tool` a las herramientas y `categoria_seleccion` a las apps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())