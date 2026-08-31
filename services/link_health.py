#!/usr/bin/env python3
"""
Salud de los links de descarga de Adobe (macOS).

Verifica el estado HTTP real de cada link y distingue tres estados:

  - "ok":      HTTP 200 (link disponible)
  - "dead":    HTTP 404/410 (link eliminado del servidor, definitivo)
  - "unknown": timeout / DNS / 5xx / 403 (NO se pudo resolver: es un posible
               falso negativo, nunca bloquea por sí solo)

Un método Adobe se marca como BLOQUEADO solo si tiene links "dead" confirmados.
El estado se guarda en SYOPS_DIR/link_health.json junto con APP_VERSION:
al cambiar la versión de la app los bloqueos se resetear (los links pueden
haberse reparado en la próxima actualización).

Uso desde la app (verificación automática en background):
    from services.link_health import refresh_link_health, get_blocked_methods
    refresh_link_health()            # verifica y persiste (rápido si ya está)
    blocked = get_blocked_methods()  # set de métodos bloqueados

Revisión manual:
    python scripts/check_adobe_links.py [--refresh] [--report-only]
"""

import json
import logging
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime

from app_config import APP_VERSION, SYOPS_DIR
from catalog.data import (
    ADOBE_TOOLS,
)

logger = logging.getLogger(__name__)

STATE_FILE = SYOPS_DIR / "link_health.json"

# Métodos Adobe conocidos (para iterar en orden estable).
ADOBE_METHOD_KEYS = ("aio_macked", "aio_sice", "multilang_sice")

_TIMEOUT = 15
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SyopsPrep/1.0"

_PIXELDRAIN_RE = re.compile(r"pixeldrain\.com/u/([A-Za-z0-9]+)")


# ── Verificación de un solo link ─────────────────────────────────
def check_url(url: str, timeout: int = _TIMEOUT) -> str:
    """Verifica un link y devuelve 'ok' | 'dead' | 'unknown'."""
    if not url:
        return "unknown"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            if status in (200, 201, 202, 206):
                return "ok"
            if status in (404, 410):
                return "dead"
            return "unknown"
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "dead"
        return "unknown"
    except Exception:
        return "unknown"


def _file_id(url: str) -> str:
    """Extrae el ID del archivo de un link de Pixeldrain (o vacío)."""
    m = _PIXELDRAIN_RE.search(url or "")
    return m.group(1) if m else ""


# ── Links de cada método ─────────────────────────────────────────
def _method_links(method: str) -> list:
    """Devuelve lista de dicts {app, arch, url, version} con los links del método."""
    from catalog.adobe_helpers import _adobe_link_flat, _adobe_version, _adobe_method_sources
    source = _adobe_method_sources(method)
    if not source:
        return []
    links = []
    for app, entry in source.items():
        if isinstance(entry, list):
            for version_item in entry:
                if not isinstance(version_item, dict):
                    continue
                version = version_item.get("version", "")
                for arch in ("arm", "intel"):
                    url = _adobe_link_flat(version_item, arch)
                    if url:
                        links.append({"app": app, "arch": arch, "url": url,
                                      "version": version})
        elif isinstance(entry, dict):
            for arch in ("arm", "intel"):
                url = _adobe_link_flat(entry, arch)
                if url:
                    links.append({"app": app, "arch": arch, "url": url,
                                  "version": _adobe_version(entry, arch)})
    return links


def _method_tool_links(method: str) -> list:
    """Devuelve los links de tools necesarios para el método."""
    links = []
    for name, cfg in ADOBE_TOOLS.items():
        if method in cfg.get("for_methods", []):
            links.append({"app": name, "arch": "tool", "url": cfg["url"], "version": ""})
    return links


def check_method(method: str) -> dict:
    """Verifica todos los links de un método.
    Devuelve {ok: [...], dead: [...], unknown: [...], blocked: bool}.
    """
    all_links = _method_links(method) + _method_tool_links(method)
    ok, dead, unknown = [], [], []
    for item in all_links:
        status = check_url(item["url"])
        item = dict(item, file=_file_id(item["url"]), status=status)
        if status == "ok":
            ok.append(item)
        elif status == "dead":
            dead.append(item)
        else:
            unknown.append(item)
    return {"ok": ok, "dead": dead, "unknown": unknown,
            "blocked": bool(dead)}


# ── Consultas para el flujo de descarga ──────────────────────────
def is_url_known_dead(url: str) -> bool:
    """True si la URL está marcada como muerta en el estado guardado.

    Usada por _adobe_best_link para elegir la versión viva sin repetir la
    verificación de red. Si no hay estado, devuelve False (asume vivo).
    """
    if not url:
        return True
    state = load_state()
    if state.get("app_version") != APP_VERSION:
        return False
    report = state.get("report", {})
    for method_report in report.values():
        for item in method_report.get("dead", []):
            if item.get("url") == url:
                return True
    return False


# ── Estado persistido ────────────────────────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict):
    try:
        SYOPS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception:
        pass


def get_blocked_methods() -> set:
    """Devuelve los métodos bloqueados para la versión actual de la app.
    Si el estado fue generado por otra versión, no hay bloqueos (reset).
    """
    state = load_state()
    if state.get("app_version") != APP_VERSION:
        return set()
    return set(state.get("blocked", []))


def is_method_blocked(method: str) -> bool:
    return method in get_blocked_methods()


# ── Verificación completa ────────────────────────────────────────
def check_app_tools() -> dict:
    """Verifica los links de las tools por app (APP_TOOLS).
    Devuelve {app: [ {name, url, file, status} ]}.
    """
    from catalog.tools import APP_TOOLS
    result = {}
    for app, tools in APP_TOOLS.items():
        items = []
        for t in tools:
            url = t.get("url", "")
            status = check_url(url)
            items.append({"name": t.get("name", app), "url": url,
                          "file": _file_id(url), "status": status})
        result[app] = items
    return result


def refresh_link_health(force: bool = False) -> dict:
    """Verifica todos los métodos y persiste el estado.

    Si ya existe un estado válido para esta versión y force=False, lo
    reutiliza (evita repetir la verificación de red en cada arranque).
    Devuelve {blocked: [...], report: {method: {...}}, app_tools: {...}}.
    """
    if not force:
        existing = load_state()
        if existing.get("app_version") == APP_VERSION and "blocked" in existing:
            return existing

    report = {}
    for method in ADOBE_METHOD_KEYS:
        report[method] = check_method(method)

    app_tools = check_app_tools()

    blocked = [m for m, r in report.items() if r["blocked"]]
    state = {
        "app_version": APP_VERSION,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "blocked": blocked,
        "report": report,
        "app_tools": app_tools,
    }
    save_state(state)
    return state


def run_async(on_done=None):
    """Ejecuta refresh_link_health en un thread y llama on_done(result)
    en el hilo principal vía una señal de Qt (thread-safe)."""
    from PySide6.QtCore import QObject, Signal, Qt

    class _Bridge(QObject):
        done = Signal(object)

    bridge = _Bridge()
    if on_done:
        bridge.done.connect(on_done, Qt.QueuedConnection)

    def _run():
        try:
            result = refresh_link_health()
        except Exception as e:
            logger.error("refresh error: %s", e)
            result = None
        bridge.done.emit(result)

    threading.Thread(target=_run, daemon=True).start()

