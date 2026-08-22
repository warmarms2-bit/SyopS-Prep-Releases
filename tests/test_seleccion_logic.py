"""Tests de describe_method y build_download_apps (services/seleccion_logic.py)."""

import pytest

from services.seleccion_logic import describe_method, build_download_apps
from services.resolver_gateway import HAS_RESOLVER_PACK
from catalog.specs import DOWNLOAD_METHODS

REQUIRES_PACK = pytest.mark.skipif(
    not HAS_RESOLVER_PACK, reason="requiere resolver_pack privado"
)


@REQUIRES_PACK
def test_describe_davinci_akirabox(monkeypatch):
    """DaVinci Resolve usa AkiraBox como resolver."""
    import importlib
    sl = importlib.import_module("services.seleccion_logic")
    monkeypatch.setattr(
        sl, "_resolve_download_link",
        lambda app: ("http", "https://akirabox.com/files/FakeABC123"),
    )
    assert sl.describe_method("DaVinci Resolve", "http") == "akirabox"


def test_describe_method_no_toca_metodos_especificos():
    """Los métodos concretos (torrent, GenP) no se sobrescriben."""
    assert describe_method("Alguna App", "torrent") == "torrent"
    assert describe_method("GenP", "GenP") == "GenP"


def test_describe_no_crashea_app_desconocida():
    """App sin link no rompe y devuelve algo razonable."""
    result = describe_method("App Inexistente XYZ", "http")
    assert isinstance(result, str)
    assert result


def test_office_expande_en_subapps():
    """Office (group) se expande en sub-apps + core components."""
    assert DOWNLOAD_METHODS.get("Office") == "group"
    result = build_download_apps(["Office"], ["Word", "Excel"], [])
    assert "Word" in result
    assert "Excel" in result
    assert "Microsoft AutoUpdate (MAU)" in result
    assert "Office" not in result


def test_office_sube_con_otras_apps():
    """Office se expande y las otras apps se mantienen."""
    result = build_download_apps(["Office", "SketchUp Pro"], ["Word"], [])
    assert "Word" in result
    assert "SketchUp Pro" in result
    assert "Office" not in result
