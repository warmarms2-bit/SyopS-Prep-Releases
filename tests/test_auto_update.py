"""Tests de la autoactualización (services/auto_update.py).

Sin red: se mockea fetch_latest_version. Verifican la comparación de
versiones y la lógica de decisión.
"""

import pytest

from services import auto_update


def test_parse_versions():
    assert auto_update._parse_version("1.0.0") == (1, 0, 0)
    assert auto_update._parse_version("2.10.1") == (2, 10, 1)
    assert auto_update._parse_version("") == (0,)
    assert auto_update._parse_version("abc") == (0,)


def test_no_update_cuando_igual(monkeypatch):
    monkeypatch.setattr(auto_update, "APP_VERSION", "1.1.0")
    monkeypatch.setattr(auto_update, "fetch_latest_version", lambda *a, **k: "1.1.0")
    hay, nueva, actual = auto_update.check_for_update()
    assert hay is False
    assert nueva == "1.1.0"
    assert actual == "1.1.0"


def test_no_update_cuando_vieja(monkeypatch):
    monkeypatch.setattr(auto_update, "APP_VERSION", "1.2.0")
    monkeypatch.setattr(auto_update, "fetch_latest_version", lambda *a, **k: "1.1.0")
    hay, _, _ = auto_update.check_for_update()
    assert hay is False


def test_hay_update(monkeypatch):
    monkeypatch.setattr(auto_update, "APP_VERSION", "1.0.0")
    monkeypatch.setattr(auto_update, "fetch_latest_version", lambda *a, **k: "1.1.0")
    hay, nueva, actual = auto_update.check_for_update()
    assert hay is True
    assert nueva == "1.1.0"
    assert actual == "1.0.0"


def test_sin_conexion_no_rompe(monkeypatch):
    monkeypatch.setattr(auto_update, "APP_VERSION", "1.0.0")
    monkeypatch.setattr(auto_update, "fetch_latest_version", lambda *a, **k: None)
    hay, nueva, actual = auto_update.check_for_update()
    assert hay is False
    assert nueva is None
