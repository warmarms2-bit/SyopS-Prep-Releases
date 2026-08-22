"""Tests de DownloadEngine (services/download_engine.py).

El conftest stubbea PySide6 (señales no-op), así que probamos las
funciones puras y la selección de estrategia sin red ni Qt real.
"""



from services.download_engine import _http_headers, _clean_cd_name, DownloadEngine


def test_http_headers_user_agent():
    h = _http_headers("https://example.com/file")
    assert "User-Agent" in h
    assert "Chrome" in h["User-Agent"]


def test_http_headers_akirabox_referer():
    h = _http_headers("https://akirabox.com/file/abc")
    assert h.get("Referer") == "https://akirabox.to/"


def test_http_headers_otro_host_sin_referer():
    h = _http_headers("https://pixeldrain.com/u/abc")
    assert "Referer" not in h


def test_clean_cd_name_url_encoded():
    assert _clean_cd_name("Photo%20Editor.pkg") == "Photo Editor.pkg"


def test_clean_cd_name_reemplaza_slashes():
    assert _clean_cd_name("a/b\\c.pkg") == "a_b_c.pkg"


def test_clean_cd_name_vacio():
    assert _clean_cd_name("") == ""
    assert _clean_cd_name(None) is None


def test_engine_constructor():
    """El engine se crea con las señales de progreso/completado."""
    engine = DownloadEngine()
    assert hasattr(engine, "progress")
    assert hasattr(engine, "completed")


def test_engine_tiene_metodos_esenciales():
    engine = DownloadEngine()
    for m in ("download_http", "shutdown", "stop_surge"):
        assert hasattr(engine, m), f"falta {m}"
