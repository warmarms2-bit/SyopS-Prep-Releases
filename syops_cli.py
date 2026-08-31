#!/usr/bin/env python3
"""SyopS Prep — Terminal (CLI del dominio).

Usa SOLO el dominio puro (catalog/, services/, system/, app_config.py):
sin PySide6 y sin la capa de UI. La interfaz gráfica (ui/) es una capa
opcional que se pone encima para el cliente.

Comandos:
  info                Datos del equipo + app
  categorias          Categorías y programas disponibles
  metodos [APP]       Método(s) de descarga de una app (o resumen)
  status              Estado de la licencia/activación
  activar <CODIGO>    Verificar y guardar un código de activación
  check               Salud de los métodos (links)
  descargar APPS...   Descargar apps (--office A,B --adobe-metodo X --dir DIR)

Ejemplos:
  python3 syops_cli.py info
  python3 syops_cli.py categorias
  python3 syops_cli.py metodos Photoshop
  python3 syops_cli.py status
  python3 syops_cli.py activar 7F3A-9C2B
  python3 syops_cli.py descargar Photoshop Illustrator --adobe-metodo macked
  python3 syops_cli.py descargar Office --office Word,Excel
"""

import argparse
import asyncio
import sys
from pathlib import Path

from i18n import _
from app_config import APP_VERSION, SYOPS_DIR, MAX_CONCURRENT
from catalog.data import SOFTWARE_CATEGORIES, ADOBE_APPS, DOWNLOAD_METHODS, ADOBE_METHODS
from services.seleccion_logic import build_download_apps, describe_method
from services.download_resolvers import (
    _write_instructions_file, _missing_download_links,
)
from services.resolver_gateway import _resolve_download_link, is_appstorrent_url
from services.download_engine import DownloadEngine
from services.download_manager import DownloadManager
from services.link_health import get_blocked_methods, check_method
from system.hardware import get_hwid, get_machine_id, get_system_scan_info


def _print(txt=""):
    print(txt, flush=True)


def cmd_info(args):
    """Datos del equipo + app."""
    client_id, hwid = get_machine_id(), get_hwid()
    scan = get_system_scan_info()
    _print(f"SyopS Prep v{APP_VERSION}")
    _print(f"  Cliente ID : {client_id}")
    _print(f"  Hardware ID: {hwid}")
    _print(f"  Directorio : {SYOPS_DIR}")
    _print(f"  CPU        : {scan.get('cpu')}")
    _print(f"  RAM        : {scan.get('ram')} GB")
    disk = scan.get("disk", {})
    free_gb = disk.get("free_gb") or disk.get("free")
    _print(f"  Disco libre: {free_gb} GB")
    _print(f"  OS         : {scan.get('os')}")


def cmd_categorias(args):
    """Lista categorías y programas."""
    for cat, info in SOFTWARE_CATEGORIES.items():
        _print(f"[{_(info.get('label_key', cat))}]")
        for app in info.get("apps", []):
            method = DOWNLOAD_METHODS.get(app)
            tag = "  (descargable)" if method else ""
            _print(f"  - {app}{tag}")
        _print()


def cmd_metodos(args):
    """Método(s) de descarga de una app."""
    if args.app:
        app = args.app.strip()
        if app in ADOBE_APPS:
            _print(f"Adobe '{app}':")
            for m in ADOBE_METHODS:
                _print(f"  - {m}  →  {describe_method(app, m) or '(sin detalle)'}")
            return
        method = DOWNLOAD_METHODS.get(app)
        if method is None:
            _print(f"'{app}' no está en el catálogo de descargas.")
            return
        link, err = _resolve_download_link(app)
        _print(f"{app}: método={method} | link={link or err}")
        return
    # Resumen: métodos disponibles por categoría
    for cat, info in SOFTWARE_CATEGORIES.items():
        desc = [f"{a} ({DOWNLOAD_METHODS.get(a)})" for a in info.get("apps", [])
                if DOWNLOAD_METHODS.get(a)]
        if desc:
            _print(f"[{_(info.get('label_key', cat))}] " + ", ".join(desc))


def cmd_status(args):
    """Estado de la licencia."""
    client_id, hwid = get_machine_id(), get_hwid()
    from services.activation import (
        is_activated, get_activated_max_apps, get_activation_type,
    )
    ok = is_activated(SYOPS_DIR, client_id, hwid)
    _print(f"Activado : {'SÍ' if ok else 'NO'}")
    if ok:
        _print(f"Máx apps: {get_activated_max_apps(SYOPS_DIR, client_id, hwid)}")
        _print(f"Tipo     : {get_activation_type(SYOPS_DIR, client_id, hwid)}")
    else:
        _print("Ejecutá: python3 syops_cli.py activar <CODIGO>")


def cmd_activar(args):
    """Verificar y guardar un código de activación."""
    from services.activation import verify_activation_code, save_activation_state
    client_id, hwid = get_machine_id(), get_hwid()
    ok, reason = verify_activation_code(client_id, args.codigo, hwid)
    if not ok:
        _print(f"Código INVÁLIDO: {reason}")
        sys.exit(1)
    save_activation_state(SYOPS_DIR, client_id, args.codigo, reason, hwid)
    _print(f"Código válido (tipo: {reason}). Activación guardada.")


def cmd_check(args):
    """Salud de los métodos (links)."""
    blocked = get_blocked_methods()
    _print("Métodos bloqueados/muertos:" if blocked else "Sin métodos bloqueados.")
    for m in blocked:
        info = check_method(m)
        _print(f"  - {m}: {info.get('status', '?')}")


def _task_from_app(app: str, adobe_method: str, output_dir: Path):
    """Construye una DownloadTask para una app (delega en el planner único)."""
    from services.download_planner import _task_for_app
    return _task_for_app(app, adobe_method or "macked", output_dir)


def cmd_descargar(args):
    """Descarga las apps seleccionadas con progreso en consola."""
    output_dir = Path(args.dir or SYOPS_DIR / "descargas")
    output_dir.mkdir(parents=True, exist_ok=True)

    apps = args.apps
    office = [a.strip() for a in args.office.split(",") if a.strip()] if args.office else []
    adobe_patched = [a for a in apps if a in ADOBE_APPS and args.full_pack]
    downloadable = build_download_apps(apps, office, adobe_patched)

    if not downloadable:
        _print("Nada descargable con esa selección.")
        return

    # Validación previa: apps con método pero sin link configurado.
    missing = _missing_download_links(downloadable)
    if missing:
        _print(f"⚠  Sin link configurado (instalación manual): {', '.join(missing)}")

    # Plan de descarga único (services/download_planner.py).
    from services.download_planner import plan_downloads
    plan = plan_downloads(downloadable, output_dir,
                          args.adobe_metodo or "macked",
                          adobe_fullpack=args.full_pack)

    for w in plan.warnings:
        _print(f"⚠  {w}")
    if not plan.tasks:
        _print("No se pudo construir ninguna tarea.")
        return

    # Aviso: apps cuyo link requiere el worker de navegador (QtWebEngine).
    for name in plan.resolver_requirements:
        _print(f"  ↳ {name}: resolución por navegador worker (akirabox/appstorrent)")

    _print(f"Descargando {len(plan.tasks)} archivo(s) a: {output_dir}")
    for t in plan.tasks:
        _print(f"  • {t.name}  [{t.method}]")

    engine = DownloadEngine()
    manager = DownloadManager(engine, MAX_CONCURRENT)

    def on_progress(name, pct, status, downloaded, total):
        pct = int(pct or 0)
        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
        mb = downloaded / (1024 * 1024)
        total_mb = f"/{total / (1024 * 1024):.0f}MB" if total else ""
        _print(f"\r  {name[:28]:<28} [{bar}] {pct:>3}%  {mb:.0f}MB{total_mb}  {status}", end="")

    def on_completed(name, success, size):
        _print(f"\r  {name[:28]:<28} {'✓ LISTO' if success else '✗ FALLÓ'}"
               f"  ({size / (1024 * 1024):.1f} MB)" if success else
               f"\r  {name[:28]:<28} ✗ FALLÓ")

    manager.task_progress.connect(on_progress)
    manager.task_completed.connect(on_completed)
    for t in plan.tasks:
        manager.add_task(t)

    asyncio.run(manager.start_all())
    _print()
    failed = [t for t in plan.tasks if t.status == "failed"]
    _print(f"Finalizado. {len(plan.tasks) - len(failed)}/{len(plan.tasks)} completados.")
    for t in failed:
        _print(f"  ✗ {t.name}: {t.error_msg or 'error desconocido'}")

    # Instrucciones de instalación (igual que la UI al finalizar).
    instrucciones_apps = list(apps) + office + (["GenP"] if args.full_pack and adobe_patched else [])
    _write_instructions_file(output_dir, instrucciones_apps)
    if (output_dir / "instrucciones.txt").exists():
        _print(f"Instrucciones de instalación: {output_dir / 'instrucciones.txt'}")

    # Whitelist de Windows Defender (solo Windows, opcional).
    if args.whitelist:
        import sys as _sys
        if _sys.platform == "win32":
            try:
                from system.hardware import whitelist_defender
                whitelist_defender(SYOPS_DIR)
                _print("Whitelist de Windows Defender aplicada.")
            except Exception as e:
                _print(f"⚠  No se pudo aplicar whitelist: {e}")
        else:
            _print("Whitelist solo aplica en Windows — omitida.")


def cmd_resolver(args):
    """Resuelve el link directo de una URL de file-host (sin descargar).

    AkiraBox/Appstorrent están detrás de Cloudflare managed challenge:
    no se pueden resolver con HTTP puro (probado: urllib, curl,
    cloudscraper, endpoints directos). Se usa el worker de navegador
    (QtWebEngine, subprocess) que pasa el challenge. Si PySide6 no está
    instalado, el comando lo avisa.
    """
    url = args.url
    from services.resolver_gateway import (
        is_akirabox_url,
        make_akirabox_resolver, make_appstorrent_resolver,
        make_swisstransfer_resolver, make_seyarabata_resolver,
    )

    _print(f"Resolviendo {url} …")
    if is_akirabox_url(url):
        resolver = make_akirabox_resolver(url, app="?")
    elif is_appstorrent_url(url):
        resolver = make_appstorrent_resolver(url)
    elif "swisstransfer" in url:
        resolver = make_swisstransfer_resolver(url)
    elif "seyarabata" in url:
        resolver = make_seyarabata_resolver(url)
    else:
        _print("Tipo de host no soportado (usa akirabox/appstorrent/swisstransfer/seyarabata).")
        return

    import time
    t0 = time.time()
    try:
        resolved, headers = resolver()
        if resolved:
            _print(f"✓ LINK DIRECTO ({time.time() - t0:.0f}s):")
            _print(resolved)
            if headers:
                _print(f"  headers: {headers}")
        else:
            _print("✗ No se pudo resolver (link vacío).")
    except Exception as e:
        _print(f"✗ Falló la resolución ({time.time() - t0:.0f}s): {e}")
        _print("  Los hosts con Cloudflare (akirabox/appstorrent) requieren QtWebEngine.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="syops_cli", description="SyopS Prep — terminal (dominio puro, sin UI)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="datos del equipo + app")
    sub.add_parser("categorias", help="categorías y programas")

    pm = sub.add_parser("metodos", help="métodos de descarga")
    pm.add_argument("app", nargs="?", default=None, help="app (opcional: resumen)")

    sub.add_parser("status", help="estado de la activación")
    pa = sub.add_parser("activar", help="verificar y guardar código")
    pa.add_argument("codigo")

    sub.add_parser("check", help="salud de los métodos")

    pr = sub.add_parser("resolver", help="link directo de un file-host sin descargar")
    pr.add_argument("url")

    pd = sub.add_parser("descargar", help="descargar apps")
    pd.add_argument("apps", nargs="+")
    pd.add_argument("--office", default=None, help="sub-apps de Office, ej: Word,Excel")
    pd.add_argument("--adobe-metodo", default=None, help=f"método Adobe ({', '.join(ADOBE_METHODS)})")
    pd.add_argument("--full-pack", action="store_true", help="Adobe full pack (links del paquete)")
    pd.add_argument("--dir", default=None, help="carpeta de salida")
    pd.add_argument("--whitelist", action="store_true", help="whitelist de Windows Defender (Windows)")

    args = p.parse_args(argv)
    {
        "info": cmd_info, "categorias": cmd_categorias, "metodos": cmd_metodos,
        "status": cmd_status, "activar": cmd_activar, "check": cmd_check,
        "resolver": cmd_resolver, "descargar": cmd_descargar,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
