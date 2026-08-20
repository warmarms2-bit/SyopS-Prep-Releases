#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  RENOVAR LINKS - Actualiza el catálogo en la hoja tras re-subir
#
#  Cierra el ciclo de renovación semiautomática:
#
#    1. check_catalog_links.py --server ... --key ...   → detecta dead/gui
#    2. (MANUAL) re-subir el archivo al host → nueva URL
#    3. renovar_links.py --server ... --key ... nuevo_links.csv
#         → update_link por fila en el Apps Script (sin pegar el CSV)
#
#  CSV de entrada: nombre,plataforma,url[,resolver]  (sin cabecera, o con
#  cabecera que incluya esas columnas).
#
#  Uso:  python3 tools/renovar_links.py --server URL --key CLAVE archivo.csv
# ═══════════════════════════════════════════════════════════════════

import argparse
import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _update(server: str, key: str, row: dict) -> tuple:
    """Llama update_link en el Apps Script. Devuelve (ok, mensaje)."""
    payload = json.dumps({
        "action": "update_link",
        "key": key,
        "nombre": row["nombre"],
        "plataforma": row["plataforma"],
        "method": row.get("metodo", ""),
        "url": row["url"],
        "resolver": row.get("resolver", ""),
    }).encode("utf-8")
    req = urllib.request.Request(
        server,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") == "ok":
        return True, ""
    return False, str(data.get("message", "error"))


def _read_csv(path: Path) -> list:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        first = next(reader, None)
        if first is None:
            return rows
        if any(c.strip().lower() in ("nombre", "name", "app") for c in first):
            headers = [h.strip().lower() for h in first]
            idx = {h: i for i, h in enumerate(headers)}
            rows.append([row for row in reader])
            # rebuild as dicts
            dicts = []
            for vals in rows[0]:
                if len(vals) < 3:
                    continue
                d = {"nombre": vals[idx["nombre"]],
                     "plataforma": vals[idx.get("plataforma", idx.get("platform", 2))]}
                d["url"] = vals[idx.get("url", 3)] if "url" in idx else vals[3]
                d["metodo"] = vals[idx["metodo"]] if "metodo" in idx else ""
                d["resolver"] = vals[idx["resolver"]] if "resolver" in idx else ""
                dicts.append(d)
            return dicts
        # sin cabecera: nombre, plataforma, url[, resolver]
        dicts = []
        for vals in [first] + list(reader):
            if len(vals) < 3 or not vals[0].strip():
                continue
            dicts.append({
                "nombre": vals[0].strip(),
                "plataforma": vals[1].strip(),
                "url": vals[2].strip(),
                "metodo": "",
                "resolver": vals[3].strip() if len(vals) > 3 else "",
            })
        return dicts


def main():
    parser = argparse.ArgumentParser(description="Renovación de links en la hoja")
    parser.add_argument("csv", help="archivo CSV: nombre,plataforma,url[,resolver]")
    parser.add_argument("--server", default=os.environ.get("SYOPS_SELLER_URL", ""), required=False,
                        help="URL /exec del Apps Script")
    parser.add_argument("--key", default=os.environ.get("SYOPS_SELLER_KEY", ""),
                        help="clave de vendedor")
    args = parser.parse_args()

    if not args.server or not args.key:
        raise SystemExit("Faltan --server y/o --key (o las env SYOPS_SELLER_URL/SYOPS_SELLER_KEY).")

    rows = _read_csv(Path(args.csv))
    if not rows:
        raise SystemExit(f"No se leyeron filas de {args.csv}")

    ok = 0
    for row in rows:
        good, msg = _update(args.server, args.key, row)
        tag = "✓" if good else "✗"
        extra = f"  ({msg})" if msg else ""
        print(f"  {tag} {row['plataforma']:<4} {row['nombre']:<32} {row['url']}{extra}")
        if good:
            ok += 1

    print(f"\n  Actualizados: {ok}/{len(rows)}")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())