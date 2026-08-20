#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  CHECK CATALOG LINKS - Salud del catálogo (resolver-aware)
#
#  Responde a la pregunta "¿hay links muertos o son los resolvers?"
#  distinguiendo, por cada link del catálogo (catalog/urls.py + tools):
#
#    ok      → el host confirma que el archivo existe (API/HEAD/302)
#    dead    → el host dice EXPLÍCITAMENTE que ya no existe (404/410 o
#              respuesta "no files")
#    gui     → requiere worker QWebEngine/sesión de navegador (akirabox,
#              appstorrent): NO se puede confirmar desde CLI; nunca es dead
#    unknown → no se pudo confirmar (timeout/DNS/5xx/403): posible falso
#              negativo, no se trata como muerto
#
#  REGLA: solo "dead" implica renovar. "unknown"/"gui" nunca bloquean.
#
#  Uso:  python3 tools/check_catalog_links.py [--json] [--solo-muertos]
#                                        [--limit N] [--workers N]
# ═══════════════════════════════════════════════════════════════════

import argparse
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import pixeldrain_helpers as pdh
from services import public_resolvers as pub
from tools.exportar_links import build_rows

OK, DEAD, GUI, UNKNOWN = "ok", "dead", "gui", "unknown"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SyopsCk/1.0"


# ── Fuente del catálogo ───────────────────────────────────────────
def _fetch_seller_rows(server: str, key: str) -> list:
    """Descarga el catálogo completo desde el Apps Script (get_links_seller).

    Solo responde con la clave de vendedor (Script Properties), así que el
    check se hace sobre el catálogo REAL de la hoja sin reabrir el leak.
    """
    url = server + "?action=get_links_seller&key=" + urllib.parse.quote(key)
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "ok":
        raise SystemExit(f"get_links_seller falló: {data}")
    rows = []
    for r in data.get("links", []):
        rows.append([
            r.get("nombre", ""),
            r.get("metodo", ""),
            r.get("plataforma", ""),
            r.get("url", ""),
            r.get("resolver", ""),
        ])
    return rows


def _load_rows(server: str | None, key: str) -> list:
    if server:
        if not key:
            raise SystemExit("Falta --key (clave de vendedor) para leer la hoja.")
        print(f"  Leyendo catálogo desde la hoja: {server}")
        return _fetch_seller_rows(server, key)
    rows = build_rows()
    if not rows:
        print("  ⚠  catalog/urls.py local no trae URLs (repo censurado).")
        print("     Usá --server URL --key CLAVE para verificar el catálogo de la hoja.")
    return rows


# ── Chequeos por host ─────────────────────────────────────────────
def _check_pixeldrain(url: str) -> str:
    fid = pdh._pixeldrain_file_id(url)
    if not fid:
        return UNKNOWN
    try:
        req = urllib.request.Request(
            f"https://pixeldrain.com/api/file/{fid}/info",
            headers={"User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("success"):
            return OK
        msg = str(data.get("value") or data.get("error") or "").lower()
        if "not found" in msg or "does not exist" in msg or "404" in msg:
            return DEAD
        return UNKNOWN
    except urllib.error.HTTPError as e:
        return DEAD if e.code in (404, 410) else UNKNOWN
    except Exception:
        return UNKNOWN


def _check_swisstransfer(url: str) -> str:
    uuid = pub._swisstransfer_link_uuid(url)
    if not uuid:
        return UNKNOWN
    try:
        data = pub._swisstransfer_link_info(uuid)
        if (data.get("files") or []):
            return OK
        return DEAD  # "No se encontraron archivos": link muerto confirmado
    except Exception:
        return UNKNOWN


def _check_seyarabata(url: str) -> str:
    try:
        resolved = pub.resolve_seyarabata_url(url, timeout=15, retries=0)
        return OK if resolved else UNKNOWN
    except urllib.error.HTTPError as e:
        return DEAD if e.code in (404, 410) else UNKNOWN
    except Exception:
        return UNKNOWN


def _check_workupload(url: str) -> str:
    """Workupload: la sesión+puzzle resuelve en CLI; los errores de red no
    implican link muerto (el token es efímero)."""
    try:
        resolved = pub.resolve_workupload_with_session(url, timeout=20)
        return OK if resolved else UNKNOWN
    except Exception:
        return UNKNOWN


def _check_http(url: str) -> str:
    if url.startswith("magnet:"):
        return OK
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Range": "bytes=0-0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.getcode()
        return OK if code in (200, 201, 202, 206) else UNKNOWN
    except urllib.error.HTTPError as e:
        return DEAD if e.code in (404, 410) else UNKNOWN
    except Exception:
        return UNKNOWN


def _check_row(row: list) -> dict:
    name = row[0]
    metodo = row[1]
    plataforma = row[2]
    url = row[3]
    resolver = row[4]

    if resolver == "pixeldrain":
        status = _check_pixeldrain(url)
    elif resolver == "swisstransfer":
        status = _check_swisstransfer(url)
    elif resolver == "seyarabata":
        status = _check_seyarabata(url)
    elif resolver == "workupload":
        status = _check_workupload(url)
    elif resolver in ("akirabox", "appstorrent"):
        status = GUI  # requiere worker QWebEngine: no verificable en CLI
    elif url.startswith("http"):
        status = _check_http(url)
    elif url.startswith("magnet:"):
        status = OK
    else:
        status = UNKNOWN

    return {
        "nombre": name,
        "metodo": metodo,
        "plataforma": plataforma,
        "resolver": resolver,
        "url": url,
        "status": status,
    }


# ── Reporte ───────────────────────────────────────────────────────
def _summary(results: list) -> dict:
    counts = {OK: 0, DEAD: 0, GUI: 0, UNKNOWN: 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def _print_report(results, solo_muertos: bool):
    counts = _summary(results)
    print()
    print("  RESUMEN DE SALUD DEL CATÁLOGO")
    print(f"    total   : {len(results)}")
    print(f"    ok      : {counts[OK]}")
    print(f"    dead    : {counts[DEAD]}")
    print(f"    gui     : {counts[GUI]}  (worker requerido, no verificables en CLI)")
    print(f"    unknown : {counts[UNKNOWN]}  (no pudo confirmarse, no bloquea)")
    print()

    if counts[DEAD]:
        print(f"  → LINKS MUERTOS ({counts[DEAD]}): re-upload y actualizar la hoja")
        for r in results:
            if r["status"] == DEAD:
                print(f"    [{r['plataforma']}/{r['resolver']}] {r['nombre']:<32} {r['url']}")
        print()
    if not solo_muertos:
        for r in results:
            if r["status"] == UNKNOWN:
                print(_c(f"  ?[{r['plataforma']}/{r['resolver']}] {r['nombre']}  {r['url']}", "33"))
        for r in results:
            if r["status"] == GUI:
                print(_c(f"  ~[{r['plataforma']}/{r['resolver']}] {r['nombre']}  {r['url']}", "36"))


def _c(text, code):
    return f"\033[{code}m{text}\033[0m"


def main():
    parser = argparse.ArgumentParser(description="Salud del catálogo (resolver-aware)")
    parser.add_argument("--json", action="store_true", help="guardar catalog_health.json")
    parser.add_argument("--solo-muertos", action="store_true",
                        help="mostrar solo dead/gui/unknown (sin ok)")
    parser.add_argument("--limit", type=int, default=0, help="verificar solo las primeras N filas")
    parser.add_argument("--workers", type=int, default=10, help="checks en paralelo")
    parser.add_argument("--server", default=os.environ.get("SYOPS_SELLER_URL", ""),
                        help="URL /exec del Apps Script (lee el catálogo de la hoja)")
    parser.add_argument("--key", default=os.environ.get("SYOPS_SELLER_KEY", ""),
                        help="clave de vendedor (Script Properties SYOPS_SELLER_KEY)")
    args = parser.parse_args()

    rows = _load_rows(args.server or None, args.key)
    limit = args.limit or len(rows)
    rows = rows[:limit]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = [r for r in ex.map(_check_row, rows)]

    _print_report(results, args.solo_muertos)

    if args.json:
        out = {
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": _summary(results),
            "rows": results,
        }
        path = ROOT / "catalog_health.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Estado guardado en {path}")


if __name__ == "__main__":
    main()