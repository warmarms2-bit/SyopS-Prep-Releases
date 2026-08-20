"""Catálogo servido por la hoja Links (categorías) + fallback local."""

import json

from services.server_catalog import (
    build_catalog,
    fetch_catalog_index,
)

LOCAL = {
    "office": {"label_key": "categoria.office", "apps": ["Word", "Excel"]},
    "general": {"label_key": "categoria.general", "apps": ["Winrar", "7Zip"]},
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _n):
        return json.dumps(self._payload).encode("utf-8")


def _fake_open_ok(monkeypatch):
    def _urlopen(_req, timeout=0):
        return _FakeResp({"status": "ok", "items": [{"nombre": "Word",
                                                      "plataforma": "mac",
                                                      "categoria": "Oficina"}]})
    monkeypatch.setattr("urllib.request.urlopen", _urlopen)


def test_build_catalog_agrupa_por_categoria():
    items = [
        {"nombre": "Word", "plataforma": "mac", "categoria": "Oficina"},
        {"nombre": "Excel", "plataforma": "mac", "categoria": "Oficina"},
        {"nombre": "Photoshop", "plataforma": "mac", "categoria": "Adobe"},
    ]
    cat = build_catalog(items, "mac", LOCAL)
    assert cat["Oficina"]["apps"] == ["Word", "Excel"]
    assert cat["Oficina"]["label"] == "Oficina"
    assert cat["Adobe"]["apps"] == ["Photoshop"]


def test_build_catalog_filtra_por_so():
    items = [
        {"nombre": "Word", "plataforma": "mac", "categoria": "Oficina"},
        {"nombre": "Excel", "plataforma": "win", "categoria": "Oficina"},
    ]
    cat = build_catalog(items, "win", LOCAL)
    assert cat["Oficina"]["apps"] == ["Excel"]


def test_build_catalog_sin_so_entra():
    items = [{"nombre": "Winrar", "plataforma": "", "categoria": ""}]
    cat = build_catalog(items, "win", LOCAL)
    assert cat
    assert cat["general"]["apps"] == ["Winrar"]
    assert cat["general"]["label_key"] == "categoria.general"


def test_build_catalog_categoria_vacia_cae_al_local():
    items = [{"nombre": "Word", "plataforma": "mac", "categoria": ""}]
    cat = build_catalog(items, "mac", LOCAL)
    assert cat
    entry = cat["office"]
    assert entry["label"] is None
    assert entry["label_key"] == "categoria.office"
    assert entry["apps"] == ["Word"]


def test_build_catalog_sin_match_local_al_bucket_otra():
    items = [{"nombre": "AppNueva", "plataforma": "mac", "categoria": ""}]
    cat = build_catalog(items, "mac", LOCAL)
    assert cat["Otra"]["apps"] == ["AppNueva"]


def test_build_catalog_vacio_devuelve_none():
    assert build_catalog([], "mac", LOCAL) is None
    assert build_catalog(
        [{"nombre": "Word", "plataforma": "win", "categoria": ""}], "mac", LOCAL,
    ) is None


def test_fetch_catalog_index_ok(monkeypatch):
    _fake_open_ok(monkeypatch)
    items = fetch_catalog_index("https://script.example/exec", timeout=1)
    assert items == [{"nombre": "Word", "plataforma": "mac", "categoria": "Oficina"}]


def test_fetch_catalog_index_err(monkeypatch):
    def _boom(_req, timeout=0):
        raise OSError("no network")
    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert fetch_catalog_index("https://script.example/exec", timeout=1) is None
    assert fetch_catalog_index("", timeout=1) is None


def test_fetch_catalog_index_respuesta_invalida(monkeypatch):
    def _bad(_req, timeout=0):
        return _FakeResp({"status": "error"})
    monkeypatch.setattr("urllib.request.urlopen", _bad)
    assert fetch_catalog_index("https://script.example/exec", timeout=1) is None
    def _bad2(_req, timeout=0):
        return _FakeResp([])
    monkeypatch.setattr("urllib.request.urlopen", _bad2)
    assert fetch_catalog_index("https://script.example/exec", timeout=1) is None