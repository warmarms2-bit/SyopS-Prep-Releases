"""Tests de los helpers de links/versiones Adobe (catalog/adobe_helpers.py)."""

from catalog.adobe_helpers import (
    _adobe_link_flat, _adobe_version, _adobe_versions_for_app,
    _adobe_version_count, _adobe_versions_list, _adobe_method_sources,
)


def _entry(arm_url, intel_url, version="1.0 2026"):
    return {"version": version,
            "arm":   {"url": arm_url, "resolver": "pixeldrain"},
            "intel": {"url": intel_url, "resolver": "pixeldrain"}}


def test_adobe_link_flat_dict():
    """_adobe_link_flat extrae la URL de un dict anidado."""
    entry = _entry("https://pixeldrain.com/u/AAA", "https://pixeldrain.com/u/BBB")
    assert _adobe_link_flat(entry, "arm") == "https://pixeldrain.com/u/AAA"
    assert _adobe_link_flat(entry, "intel") == "https://pixeldrain.com/u/BBB"


def test_adobe_link_flat_string():
    """_adobe_link_flat soporta el formato plano antiguo {arch: url}."""
    entry = {"arm": "https://pixeldrain.com/u/AAA", "intel": "https://pixeldrain.com/u/BBB"}
    assert _adobe_link_flat(entry, "arm") == "https://pixeldrain.com/u/AAA"
    assert _adobe_link_flat(entry, "intel") == "https://pixeldrain.com/u/BBB"


def test_adobe_link_flat_none():
    assert _adobe_link_flat(None, "arm") == ""
    assert _adobe_link_flat({"arm": {"url": None}}, "arm") == ""


def test_adobe_version():
    entry = _entry("u/A", "u/B", version="30.2.1 2026")
    assert _adobe_version(entry, "arm") == "30.2.1 2026"
    # Formato plano ({arch: url}) no tiene versión
    assert _adobe_version({"arm": "u/A", "intel": "u/B"}, "arm") == ""


def test_adobe_versions_for_app_sice(monkeypatch):
    """Illustrator en SICE tiene al menos una versión con link arm e intel."""
    import catalog.adobe_helpers as adobe_helpers
    monkeypatch.setattr(
        adobe_helpers, "_adobe_method_sources",
        lambda m: {"Illustrator": [
            {"version": "30.2.1 2026",
             "arm": {"url": "https://dl.example/ill-arm", "resolver": "pixeldrain"},
             "intel": {"url": "https://dl.example/ill-intel", "resolver": "pixeldrain"}},
        ]},
    )
    versions = _adobe_versions_for_app("aio_sice", "Illustrator")
    assert versions, "Illustrator debería tener versiones en SICE"
    first = versions[0]
    assert first.get("version")
    assert _adobe_link_flat(first, "arm")
    assert _adobe_link_flat(first, "intel")


def test_adobe_version_count():
    """El conteo de versiones es >= 1 para apps presentes."""
    assert _adobe_version_count("aio_sice", "Illustrator") >= 1
    # App inexistente -> 0
    assert _adobe_version_count("aio_sice", "App Inexistente XYZ") == 0


def test_metodos_devuelven_lista():
    """Cada método expone apps con estructura de lista de versiones."""
    for method in ("aio_sice", "aio_macked", "multilang_sice"):
        source = _adobe_method_sources(method)
        assert source, f"{method} no debería estar vacío"
        for app, entry in source.items():
            assert isinstance(entry, list), f"{method}[{app}] debería ser lista"


def test_adobe_versions_list_compat():
    """_adobe_versions_list (lista plana de versiones) funciona."""
    assert _adobe_versions_list("aio_sice", "Illustrator") != []
