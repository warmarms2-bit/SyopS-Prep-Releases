"""Tests del flujo CLI: comandos de selección (0/r/q) y deselección.

Cubren el menú de `choose_apps` (agregar, '0' = salir de la categoría,
'r' = quitar elegidos) y `_quitar_apps`, además del cableado en
`_seleccion` cuando el usuario sale de una categoría.
"""

import pytest

import syops_wizard as W
from app_flow import platform_apps
from catalog.base import IS_MAC, IS_WIN


def _mac_category():
    """Primera categoría con apps para macOS (para tests en Mac)."""
    from catalog.data import SOFTWARE_CATEGORIES
    for key, info in SOFTWARE_CATEGORIES.items():
        if key == "all":
            continue
        apps = info.get("apps", [])
        if platform_apps(apps, IS_MAC, IS_WIN):
            return key, list(apps)
    raise AssertionError("sin categoría macOS en el catálogo")


@pytest.fixture
def wizard(monkeypatch):
    monkeypatch.setattr(W, "get_machine_id", lambda: "TEST-CLIENT")
    monkeypatch.setattr(W, "get_hwid", lambda: "TEST-HWID")
    return W.Wizard()


def test_choose_apps_agrega_numeros(wizard, monkeypatch):
    key, apps = _mac_category()
    wizard.cat = key
    monkeypatch.setattr(W, "_ask", lambda *a, **k: "1")
    assert wizard.choose_apps() is None
    assert wizard.selected_apps == [apps[0]]


def test_choose_apps_salir_con_cero(wizard, monkeypatch):
    key, _ = _mac_category()
    wizard.cat = key
    monkeypatch.setattr(W, "_ask", lambda *a, **k: "0")
    assert wizard.choose_apps() == "salir"
    assert wizard.selected_apps == []


def test_choose_apps_invalido_luego_cero(wizard, monkeypatch):
    key, _ = _mac_category()
    wizard.cat = key
    respuestas = iter(["abc", "0"])
    monkeypatch.setattr(W, "_ask", lambda *a, **k: next(respuestas))
    assert wizard.choose_apps() == "salir"
    assert wizard.selected_apps == []


def test_choose_apps_r_quita_y_cero_sale(wizard, monkeypatch):
    key, apps = _mac_category()
    wizard.cat = key
    wizard.selected_apps = [apps[0], apps[1]]
    # "r" → _quitar_apps → "1" (quitar apps[0]) → vuelve al menú → "0"
    respuestas = iter(["r", "1", "0"])
    monkeypatch.setattr(W, "_ask", lambda *a, **k: next(respuestas))
    assert wizard.choose_apps() == "salir"
    assert wizard.selected_apps == [apps[1]]


def test_quitar_apps_cancela_con_cero(wizard, monkeypatch):
    wizard.selected_apps = ["App A", "App B"]
    monkeypatch.setattr(W, "_ask", lambda *a, **k: "0")
    wizard._quitar_apps()
    assert wizard.selected_apps == ["App A", "App B"]


def test_quitar_apps_remueve(wizard, monkeypatch):
    wizard.selected_apps = ["App A", "App B"]
    monkeypatch.setattr(W, "_ask", lambda *a, **k: "1")
    wizard._quitar_apps()
    assert wizard.selected_apps == ["App B"]


def test_seleccion_salir_repregunta_categoria(wizard, monkeypatch):
    llamadas = {"cat": 0, "app": 0}

    def fake_choose_category():
        llamadas["cat"] += 1

    def fake_choose_apps():
        if llamadas["app"] == 0:
            llamadas["app"] += 1
            return "salir"
        return None

    monkeypatch.setattr(wizard, "show_scan", lambda: None)
    monkeypatch.setattr(wizard, "choose_category", fake_choose_category)
    monkeypatch.setattr(wizard, "choose_apps", fake_choose_apps)
    monkeypatch.setattr(wizard, "show_resumen", lambda: True)
    monkeypatch.setattr(W, "_yes_no", lambda *a, **k: False)
    wizard.ask_adobe_question = lambda: None
    wizard.choose_adobe_method_if_needed = lambda: None

    assert wizard._seleccion() is True
    assert llamadas["cat"] == 2


def test_seleccion_pide_otra_categoria_si_afirma(wizard, monkeypatch):
    llamadas = {"cat": 0}

    def fake_choose_category():
        llamadas["cat"] += 1

    monkeypatch.setattr(wizard, "show_scan", lambda: None)
    monkeypatch.setattr(wizard, "choose_category", fake_choose_category)
    monkeypatch.setattr(wizard, "choose_apps", lambda: None)
    monkeypatch.setattr(wizard, "show_resumen", lambda: True)
    respuestas = iter([True, False])  # afirmar otra categoría → luego no
    monkeypatch.setattr(W, "_yes_no", lambda *a, **k: next(respuestas))
    wizard.ask_adobe_question = lambda: None
    wizard.choose_adobe_method_if_needed = lambda: None

    assert wizard._seleccion() is True
    assert llamadas["cat"] == 2