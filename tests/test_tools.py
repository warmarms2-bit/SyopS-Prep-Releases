"""Tests del sistema de tools por app (catalog/tools.py)."""

from catalog.tools import (
    APP_TOOLS, _app_tools_for_app, _all_app_tools, _apps_with_tools,
)


def test_app_tools_estructura():
    """Cada tool tiene name y campo url (puede venir del Sheet)."""
    for app, tools in APP_TOOLS.items():
        assert isinstance(tools, list), f"{app}: tools debe ser lista"
        for t in tools:
            assert t.get("name"), f"{app}: tool sin name"
            assert "url" in t, f"{app}: tool sin campo url"


def test_app_tools_para_app():
    """_app_tools_for_app devuelve las tools de una app (o [])."""
    assert _app_tools_for_app("SketchUp Pro") != []
    assert _app_tools_for_app("App Sin Tools XYZ") == []


def test_apps_with_tools():
    """_apps_with_tools devuelve las apps con tools registradas."""
    apps = _apps_with_tools()
    assert "SketchUp Pro" in apps
    assert "DaVinci Resolve" in apps


def test_photoshop_tiene_tools():
    """Photoshop usa patcher + Sentinel (fuentes consolidadas)."""
    names = [t["name"] for t in _app_tools_for_app("Photoshop")]
    assert any("Patcher" in n for n in names)
    assert "Sentinel" in names


def test_office_subapps_heredan_tools(monkeypatch):
    """Excel (sub-app de Office) hereda MAU y Serializer."""
    from catalog.urls import _DOWNLOAD_URLS_MAC
    from catalog.categorias import OFFICE_CORE_APPS
    for core in OFFICE_CORE_APPS:
        monkeypatch.setitem(_DOWNLOAD_URLS_MAC, core, f"https://dl.example/{core}")
    names = [t["name"] for t in _app_tools_for_app("Excel")]
    assert any("MAU" in n for n in names)
    assert any("Serializer" in n for n in names)


def test_all_app_tools_incluye_app():
    """_all_app_tools adjunta la app de origen a cada tool."""
    flat = _all_app_tools()
    assert flat, "debería haber tools"
    for t in flat:
        assert t.get("app")
        assert t.get("name")


def test_dedup_tools_entre_apps():
    """Varias apps Adobe que comparten Sentinel no deben duplicarla.

    Simula la lógica de deduplicación de la descarga: se inicializa con las
    tools del método (Sentinel) y las apps solo agregan sus patchers propios.
    """
    from catalog.adobe_helpers import _adobe_tools_for_method

    apps = ["Photoshop", "Illustrator", "InDesign"]
    method = "aio_macked"
    seen = set()
    seen.update(name for name, _ in _adobe_tools_for_method(method))
    for app in apps:
        for t in _app_tools_for_app(app):
            name = t.get("name")
            if name in seen:
                continue
            seen.add(name)
    # Sentinel solo una vez, y los patchers por app presentes.
    assert "Sentinel" in seen
    assert seen == {
        "Sentinel",
        "Adobe Genuine Pop-Up Blocker",
        "Photoshop Patcher",
        "Illustrator Patcher",
        "InDesign Patcher",
    }
