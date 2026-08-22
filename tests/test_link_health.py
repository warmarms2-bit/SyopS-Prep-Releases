"""Tests de la salud de links de Adobe (services/link_health.py)."""

import pytest

from services import link_health


@pytest.fixture
def fake_state(tmp_path, monkeypatch):
    """Redirige el archivo de estado a un tmp_path y fuerza APP_VERSION."""
    monkeypatch.setattr(link_health, "STATE_FILE", tmp_path / "link_health.json")
    monkeypatch.setattr(link_health, "APP_VERSION", "1.1.0")
    return tmp_path / "link_health.json"


def test_check_url_estados(monkeypatch):
    """check_url distingue ok (200), dead (404/410) y unknown (error de red).
    Usa mock de urlopen para ser determinista (sin depender de httpbin)."""
    import urllib.request
    import urllib.error

    class FakeResp:
        def __init__(self, status):
            self._status = status
        def getcode(self):
            return self._status
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_open(req, timeout=0):
        url = req.full_url
        if "status/200" in url:
            return FakeResp(200)
        if "status/404" in url:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        if "status/410" in url:
            raise urllib.error.HTTPError(url, 410, "gone", {}, None)
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)

    assert link_health.check_url("https://httpbin.org/status/200") == "ok"
    assert link_health.check_url("https://httpbin.org/status/404") == "dead"
    assert link_health.check_url("https://httpbin.org/status/410") == "dead"
    # URL inválida / host inexistente -> unknown (nunca dead)
    assert link_health.check_url("https://noexiste.invalid/archivo") == "unknown"
    assert link_health.check_url("") == "unknown"
    assert link_health.check_url(None) == "unknown"


def test_check_method_clasifica(monkeypatch):
    """check_method agrupa links por estado y marca blocked si hay dead.
    Usa mock de check_url para ser determinista (sin red real)."""
    # El primer link del método se marca como dead para forzar blocked=True.
    # El catálogo local no lleva URLs (viven en el Sheet): inyectamos una
    # fuente sintética para probar la clasificación.
    import importlib
    ah = importlib.import_module("catalog.adobe_helpers")
    monkeypatch.setattr(
        ah, "_adobe_method_sources",
        lambda m: {"FakeApp": {
            "arm": {"url": "https://dl.example/dead", "resolver": "pixeldrain"},
            "intel": {"url": "https://dl.example/ok", "resolver": "pixeldrain"},
        }},
    )
    first_url = "https://dl.example/dead"

    def fake_check(url):
        return "dead" if first_url and url == first_url else "ok"

    lh = importlib.import_module("services.link_health")
    monkeypatch.setattr(lh, "check_url", fake_check)
    result = lh.check_method("aio_macked")
    assert "ok" in result and "dead" in result and "unknown" in result
    assert result["blocked"] is True  # primer link mockeado como dead


def test_estado_se_resetea_por_version(fake_state):
    """Un estado guardado por otra versión de la app NO bloquea (reset)."""
    link_health.save_state({"app_version": "0.9.9", "blocked": ["aio_macked"]})
    assert link_health.get_blocked_methods() == set()


def test_estado_se_respeta_misma_version(fake_state):
    """Con la misma versión, los bloqueos guardados se aplican."""
    link_health.save_state({"app_version": "1.1.0", "blocked": ["aio_macked"]})
    assert link_health.get_blocked_methods() == {"aio_macked"}
    assert link_health.is_method_blocked("aio_macked")
    assert not link_health.is_method_blocked("aio_sice")


def test_sin_estado_no_hay_bloqueos(fake_state):
    """Sin archivo de estado, no hay métodos bloqueados."""
    assert link_health.get_blocked_methods() == set()


def test_metodos_esperados():
    """Los métodos de descarga conocidos se verifican en orden estable."""
    assert link_health.ADOBE_METHOD_KEYS == ("aio_macked", "aio_sice", "multilang_sice")
