"""Tests del planner único de descargas (services/download_planner.py).

Consolida la construcción de tareas que antes vivía duplicada en la UI,
el wizard y el CLI: estos tests fijan el comportamiento canónico.
"""

import tests.conftest  # noqa: F401  (aplica stubs de PySide6/qfluentwidgets)
from pathlib import Path

import pytest

from services.download_planner import plan_downloads, _task_for_app
from services.resolver_gateway import HAS_RESOLVER_PACK

OUT = Path("/tmp/out")


def _mock(monkeypatch, target, replacement):
    """Monkeypatch un símbolo (import perezoso del planner) y lo restaura."""
    import services.download_planner as planner
    monkeypatch.setattr(planner, target, replacement)


def test_app_generica_http(monkeypatch):
    """Una app con link http directo produce una tarea sin resolver."""
    _mock(monkeypatch, "_resolve_download_link",
          lambda app: ("http", f"https://dl.example/{app}"))
    plan = plan_downloads(["Blender"], OUT)
    assert plan.tasks
    task = plan.tasks[0]
    assert task.name == "Blender"
    assert task.method == "http"
    assert task.url_or_magnet
    assert not plan.resolver_requirements
    assert plan.ok_count == len(plan.tasks)


def test_app_manual_queda_en_warnings(monkeypatch):
    """Una app sin link (manual) no genera tarea, sí warning."""
    plan = plan_downloads(["Talon"], OUT)
    assert not plan.tasks
    assert any("Talon" in w for w in plan.warnings)


def test_genp_usa_url_propia(monkeypatch):
    plan = plan_downloads(["GenP"], OUT)
    task = plan.tasks[0]
    assert task.name == "GenP"
    assert task.method == "http"
    assert task.url_or_magnet


def test_adobe_por_metodo_baja_apps_y_tools(monkeypatch):
    """Con método Adobe (macOS): apps del método + tools, y las apps Adobe
    NO se repiten en el loop genérico."""
    _mock(monkeypatch, "_adobe_best_link",
          lambda method, app: (f"https://dl/{app}", "v1.0"))
    _mock(monkeypatch, "_adobe_tools_for_method",
          lambda method: [("ToolA", "https://dl/tool-a")])
    _mock(monkeypatch, "_adobe_full_pack_links", lambda method: [])
    plan = plan_downloads(["Photoshop", "Blender"], OUT, adobe_method="macked")
    names = [t.name for t in plan.tasks]
    assert "Photoshop v1.0" in names
    assert "ToolA" in names
    # Photoshop solo aparece UNA vez (rama Adobe, no el loop genérico).
    assert names.count("Photoshop v1.0") == 1


def test_adobe_sin_metodo_cae_al_flujo_genp(monkeypatch):
    """Windows/GenP: sin método Adobe, las apps Adobe usan links directos."""
    _mock(monkeypatch, "_resolve_download_link",
          lambda app: ("http", "https://dl/adobe"))
    plan = plan_downloads(["Photoshop"], OUT, adobe_method=None)
    # La app se baja con su link directo (flujo GenP); las tools por app
    # se agregan aparte, pero la app misma aparece exactamente una vez.
    assert [t.name for t in plan.tasks if t.name == "Photoshop"] == ["Photoshop"]


def test_full_pack_baja_collection(monkeypatch):
    _mock(monkeypatch, "_adobe_full_pack_links",
          lambda method: [("Photoshop", "https://dl/ps"),
                          ("Premiere", "")])
    plan = plan_downloads([], OUT, adobe_method="aio_macked", adobe_fullpack=True)
    assert [t.name for t in plan.tasks] == ["Photoshop"]


def test_activation_tool_advierte_y_no_baja_apps(monkeypatch):
    _mock(monkeypatch, "_adobe_best_link", lambda method, app: (None, None))
    _mock(monkeypatch, "_adobe_tools_for_method",
          lambda m: [("Sentinel", "https://dl.example/sentinel"),
                     ("AntiCC v1.7", "https://dl.example/anticc"),
                     ("Adobe ACC Runtime", "https://dl.example/acc"),
                     ("Adobe Cleaner Tool", "https://dl.example/cleaner"),
                     ("Adobe Downloader", "https://dl.example/downloader")])
    plan = plan_downloads(["Photoshop"], OUT, adobe_method="activation_tool")
    assert any("activation_tool" in w for w in plan.warnings)
    # Solo las tools del método (que se bajan igual), nunca la app.
    assert not any(t.name == "Photoshop" for t in plan.tasks)
    assert not any(t.name.startswith("Photoshop v") for t in plan.tasks)
    assert [t.name for t in plan.tasks if t.name in
            ("Sentinel", "AntiCC v1.7", "Adobe ACC Runtime",
             "Adobe Cleaner Tool", "Adobe Downloader")] == [
        "Sentinel", "AntiCC v1.7", "Adobe ACC Runtime",
        "Adobe Cleaner Tool", "Adobe Downloader",
    ]


def test_links_faltantes_en_missing(monkeypatch):
    _mock(monkeypatch, "_resolve_download_link",
          lambda app: ("http", "") if app == "X" else ("http", "https://dl/x"))
    _mock(monkeypatch, "_missing_download_links", lambda apps: ["X"])
    plan = plan_downloads(["X"], OUT)
    assert plan.missing == ["X"]


def test_tools_por_app_deduplicadas(monkeypatch):
    """Una tool compartida por varias apps se agrega UNA vez."""
    _mock(monkeypatch, "_resolve_download_link",
          lambda app: ("http", f"https://dl/{app}"))
    _mock(monkeypatch, "_app_tools_for_app",
          lambda app, items=None: [{"name": "SharedTool", "url": "https://dl/shared"}])
    plan = plan_downloads(["A", "B"], OUT)
    shared = [t for t in plan.tasks if t.name == "SharedTool"]
    assert len(shared) == 1


def test_task_for_app_delegado(monkeypatch):
    """syops_cli._task_from_app y el planner comparten la misma lógica."""
    from syops_cli import _task_from_app
    task, warn = _task_from_app("Blender", "macked", OUT)
    task2, warn2 = _task_for_app("Blender", "macked", OUT)
    assert (task is None) == (task2 is None)
    assert (warn or "") == (warn2 or "")


@pytest.mark.skipif(not HAS_RESOLVER_PACK, reason="requiere resolver_pack privado")
def test_workupload_resolver_factory_no_crash(monkeypatch):
    """make_workupload_resolver acepta `link=` (llamada del planner).

    Regresión: el factory exigía `original_url` y el planner la llamaba con
    `link=` → TypeError al construir la tarea de una app de Workupload.
    """
    _mock(monkeypatch, "_resolve_download_link",
          lambda app: ("http", "https://workupload.com/file/FakeABC123"))
    task, warn = _task_for_app("FL Studio", "http", OUT, adobe_as_regular=True)
    assert task is not None, warn
    assert task.resolver_callback is not None  # el factory se crea sin red


def test_plan_via_server_no_resuelve_urls_localmente():
    """Tier 2: con un proveedor, las URLs vienen del servidor, no del catálogo."""
    class FakeProvider:
        def __init__(self):
            self.calls = []

        def request(self, name, method, platform, kind="app"):
            self.calls.append((kind, name, method))
            return {"url": f"https://server/v1/download/tok-{name}", "name": name}

    prov = FakeProvider()
    plan = plan_downloads(["Blender", "Photoshop"], OUT,
                          adobe_method="aio_macked", link_provider=prov,
                          platform="mac")
    assert plan.tasks
    for t in plan.tasks:
        # Todas las URLs apuntan al SERVIDOR, nunca a un file-host.
        assert t.url_or_magnet.startswith("https://server/")
    # Blender va por kind=app; Photoshop (método Adobe) por kind=adobe.
    assert ("app", "Blender", "http") in prov.calls
    assert ("adobe", "Photoshop", "aio_macked") in prov.calls


def test_plan_via_server_genp_por_app():
    """Sin método Adobe (GenP), las apps Adobe se piden por kind=app."""
    class FakeProvider:
        def __init__(self):
            self.calls = []

        def request(self, name, method, platform, kind="app"):
            self.calls.append((kind, name, method))
            return {"url": f"https://server/v1/download/tok-{name}", "name": name}

    prov = FakeProvider()
    plan = plan_downloads(["Photoshop"], OUT, adobe_method=None,
                          link_provider=prov, platform="win")
    assert ("app", "Photoshop", "http") in prov.calls
    assert all(t.url_or_magnet.startswith("https://server/") for t in plan.tasks)


@pytest.mark.skipif(not HAS_RESOLVER_PACK, reason="requiere resolver_pack privado")
def test_plan_via_server_activa_solo_el_resolver_indicado():
    """Si el servidor indica `resolver`, la tarea lleva SOLO ese callback."""
    class FakeProvider:
        def request(self, name, method, platform, kind="app"):
            return {"url": "https://server/resolve/akirabox/tok",
                    "name": name,
                    "resolver": "akirabox"}

    plan = plan_downloads(["DaVinci Resolve"], OUT, adobe_method=None,
                          link_provider=FakeProvider(), platform="mac")
    assert plan.tasks
    task = plan.tasks[0]
    # El callback del resolver SOLO del kind indicado, sin recorrer la lista
    # completa de detectores de URL_RESOLVERS.
    assert task.resolver_callback is not None
    assert callable(task.resolver_callback)


def test_provider_task_resolver_desconocido_degrada_con_aviso():
    """Resolver indicado por el servidor pero no disponible → aviso + directa."""
    from services.download_planner import _provider_task

    class FakeProvider:
        def request(self, name, method, platform, kind="app"):
            return {"url": f"https://server/v1/download/tok-{name}",
                    "name": name,
                    "resolver": "dropbox"}

    task, warn = _provider_task(FakeProvider(), "app", "Blender", "http",
                                "mac", OUT, 0, 0)
    assert task is not None
    assert task.resolver_callback is None
    assert warn and "dropbox" in warn
