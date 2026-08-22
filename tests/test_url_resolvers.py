"""
Tests de regresión para el registro URL_RESOLVERS y las factories de
resolución de fuente (AkiraBox, SwissTransfer, Workupload, Pixeldrain,
Seyarabata, Appstorrent).

Cubre:
  - El orden exacto del registro (para que un reorden accidental falle).
  - El comportamiento de make_akirabox_resolver (éxito / fallback /
    doble fallo) mockeando resolve_akirabox_url y resolve_swisstransfer_url.
  - La serialización real vía _resolution_lock (threading real, sin mock
    del lock) — el test más importante.
  - Que el lock se libera incluso en el camino de excepción.
  - Que Pixeldrain NO usa el lock.
  - La semántica "primer match gana" del loop con detectores reales.

Toda la lógica vive en el paquete privado resolver_pack/. Este módulo se
salta entero si el pack no está presente (repo público sin el bundle).
"""

import threading
import time
from unittest.mock import Mock

import pytest

import tests.conftest  # noqa: F401  (aplica stubs de PySide6/qfluentwidgets)

api = pytest.importorskip("resolver_pack.api")


# ── Tests ──────────────────────────────────────────────────────────


class TestRegistry:
    """Tests sobre el registro URL_RESOLVERS (orden y loop)."""

    def test_url_resolvers_registry_order(self):
        """URL_RESOLVERS debe tener exactamente 6 entradas en el orden:
        akirabox, swisstransfer, workupload, pixeldrain, seyarabata,
        appstorrent, con sus factories correspondientes."""
        registry = list(api.URL_RESOLVERS)

        assert len(registry) == 6, (
            f"URL_RESOLVERS debe tener 6 entradas, tiene {len(registry)}"
        )

        pair_names = [(d.__name__, f.__name__) for d, f in registry]
        expected = [
            ("is_akirabox_url",        "make_akirabox_resolver"),
            ("is_swisstransfer_url",   "make_swisstransfer_resolver"),
            ("is_workupload_url",      "make_workupload_resolver"),
            ("is_pixeldrain_url",      "make_pixeldrain_resolver"),
            ("is_seyarabata_url",      "make_seyarabata_resolver"),
            ("is_appstorrent_url",     "make_appstorrent_resolver"),
        ]
        assert pair_names == expected, (
            f"Orden del registro incorrecto: {pair_names}"
        )

    def test_registry_loop_first_match_wins(self):
        """Semántica 'primer match gana': para cada tipo de link, el primer
        detector del registro que matchea debe ser el correcto (los
        detectores son mutuamente excluyentes sobre links representativos,
        por lo que el orden no debe causar routing incorrecto)."""
        registry = api.URL_RESOLVERS

        links = {
            "akirabox": "https://akirabox.com/AbCdEf90xYz1/file",
            "swisstransfer": "https://www.swisstransfer.com/d/0000a1b2-c3d4-0000-0000-000000000000",
            "workupload": "https://workupload.com/file/Afgb3XdZ5LS",
            "pixeldrain": "https://pixeldrain.com/u/AbCdEf9",
            "seyarabata": "https://www.seyarabata.com/abc12345",
            "appstorrent": "https://appstorrent.ru/games/123",
        }
        expected = {
            "akirabox": "is_akirabox_url",
            "swisstransfer": "is_swisstransfer_url",
            "workupload": "is_workupload_url",
            "pixeldrain": "is_pixeldrain_url",
            "seyarabata": "is_seyarabata_url",
            "appstorrent": "is_appstorrent_url",
        }

        for source, link in links.items():
            first_match = None
            for detector, _factory in registry:
                if detector(link):
                    first_match = detector.__name__
                    break
            assert first_match == expected[source], (
                f"Link de {source} matcheó {first_match!r}, se esperaba "
                f"{expected[source]!r}"
            )


class TestAkiraboxResolver:
    """Comportamiento de make_akirabox_resolver (éxito y fallback)."""

    def test_akirabox_success_no_fallback(self, monkeypatch):
        """Si AkiraBox resuelve bien en el primer intento, devuelve
        (link, {}) y NUNCA se llama a resolve_swisstransfer_url."""
        monkeypatch.setattr(
            api, "resolve_akirabox_url",
            lambda url, parent, timeout, retries: "https://akira-resolved.example/file",
        )
        swiss_mock = Mock()
        monkeypatch.setattr(api, "resolve_swisstransfer_url", swiss_mock)
        monkeypatch.setattr(
            api, "_get_swisstransfer_fallback",
            lambda app: "https://www.swisstransfer.com/d/xyz",
        )

        resolver = api.make_akirabox_resolver(
            "https://akirabox.com/abc/file", "DaVinci Resolve")
        result = resolver()

        assert result == ("https://akira-resolved.example/file", {})
        swiss_mock.assert_not_called()

    def test_akirabox_fails_falls_back_to_swisstransfer_success(self, monkeypatch):
        """Si AkiraBox devuelve '', se cae al fallback de SwissTransfer.
        Ambas funciones se llaman en orden: primero akira, luego swiss."""
        calls = []

        def fake_akira(url, parent, timeout, retries):
            calls.append("akira")
            return ""

        def fake_swiss(url, timeout, retries):
            calls.append("swiss")
            return "https://swiss-resolved.example/file"

        monkeypatch.setattr(api, "resolve_akirabox_url", fake_akira)
        monkeypatch.setattr(api, "resolve_swisstransfer_url", fake_swiss)
        monkeypatch.setattr(
            api, "_get_swisstransfer_fallback",
            lambda app: "https://www.swisstransfer.com/d/xyz",
        )

        resolver = api.make_akirabox_resolver(
            "https://akirabox.com/abc/file", "SomeApp")
        result = resolver()

        assert result == ("https://swiss-resolved.example/file", {})
        assert calls == ["akira", "swiss"], (
            f"Orden de llamadas incorrecto: {calls}"
        )

    def test_akirabox_and_swisstransfer_both_fail_raises(self, monkeypatch):
        """Si AkiraBox devuelve '' y SwissTransfer también, resolve()
        debe lanzar RuntimeError."""
        monkeypatch.setattr(
            api, "resolve_akirabox_url",
            lambda *a, **k: "",
        )
        monkeypatch.setattr(
            api, "resolve_swisstransfer_url",
            lambda *a, **k: "",
        )
        monkeypatch.setattr(
            api, "_get_swisstransfer_fallback",
            lambda app: "https://www.swisstransfer.com/d/xyz",
        )

        resolver = api.make_akirabox_resolver(
            "https://akirabox.com/abc/file", "SomeApp")
        with pytest.raises(RuntimeError):
            resolver()


class TestSerializationLock:
    """El lock _resolution_lock debe serializar AkiraBox y SwissTransfer."""

    def test_lock_serializes_akirabox_and_swisstransfer(self, monkeypatch):
        """EL TEST MÁS IMPORTANTE. Usa threading real y el lock real para
        probar que las resoluciones de AkiraBox y SwissTransfer NO corren
        en paralelo.

        Los timestamps de trabajo se registran DENTRO de los mocks, que
        corren bajo el lock. Así medimos el trabajo real serializado, no
        el tiempo de espera por el lock.
        """
        work = {}

        def slow_akira(url, parent, timeout, retries):
            start = time.monotonic()
            time.sleep(0.3)
            end = time.monotonic()
            work["akira"] = (start, end)
            return "https://akira-resolved.example/file"

        def slow_swiss(url, timeout, retries):
            start = time.monotonic()
            time.sleep(0.3)
            end = time.monotonic()
            work["swiss"] = (start, end)
            return "https://swiss-resolved.example/file"

        monkeypatch.setattr(api, "resolve_akirabox_url", slow_akira)
        monkeypatch.setattr(api, "resolve_swisstransfer_url", slow_swiss)
        monkeypatch.setattr(api, "_get_swisstransfer_fallback", lambda app: "")

        akira_resolver = api.make_akirabox_resolver(
            "https://akirabox.com/abc/file", "SomeApp")
        swiss_resolver = api.make_swisstransfer_resolver(
            "https://www.swisstransfer.com/d/abc")

        # Barrera para que ambos threads intenten entrar casi simultáneamente.
        barrier = threading.Barrier(2)

        def run_akira():
            barrier.wait()
            akira_resolver()

        def run_swiss():
            barrier.wait()
            swiss_resolver()

        t1 = threading.Thread(target=run_akira)
        t2 = threading.Thread(target=run_swiss)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert "akira" in work and "swiss" in work, (
            f"Ambos mocks deben haber corrido. work={work}"
        )
        a_start, a_end = work["akira"]
        s_start, s_end = work["swiss"]

        # Sin el lock, ambos intervalos de 0.3s se solapan (corren en paralelo).
        # Con el lock, uno termina antes de que el otro empiece.
        if a_start <= s_start:
            assert s_start >= a_end, (
                f"SOLAPAMIENTO: akira [{a_start:.3f},{a_end:.3f}] "
                f"swiss [{s_start:.3f},{s_end:.3f}] — el lock NO serializó"
            )
        else:
            assert a_start >= s_end, (
                f"SOLAPAMIENTO: swiss [{s_start:.3f},{s_end:.3f}] "
                f"akira [{a_start:.3f},{a_end:.3f}] — el lock NO serializó"
            )

    def test_lock_released_after_exception(self, monkeypatch):
        """Si resolve_akirabox_url lanza excepción, el lock debe quedar
        liberado después (el `with` lo libera en el camino de error)."""
        def raise_akira(url, parent, timeout, retries):
            raise RuntimeError("akira exploded")

        monkeypatch.setattr(api, "resolve_akirabox_url", raise_akira)
        monkeypatch.setattr(
            api, "_get_swisstransfer_fallback",
            lambda app: "https://www.swisstransfer.com/d/xyz",
        )

        resolver = api.make_akirabox_resolver(
            "https://akirabox.com/abc/file", "SomeApp")
        with pytest.raises(RuntimeError):
            resolver()

        acquired = api._resolution_lock.acquire(blocking=False)
        assert acquired, "El lock NO fue liberado después de la excepción"
        api._resolution_lock.release()


class TestPixeldrainResolver:
    """Pixeldrain no usa el lock (transformación de URL instantánea)."""

    def test_pixeldrain_no_lock_needed(self):
        """make_pixeldrain_resolver().resolve() responde instantáneamente
        incluso mientras _resolution_lock está tomado por otro thread."""
        assert api._resolution_lock.acquire(blocking=False), (
            "No se pudo adquirir el lock para el test"
        )
        try:
            resolver = api.make_pixeldrain_resolver(
                "https://pixeldrain.com/u/abc123")
            start = time.monotonic()
            result = resolver()
            elapsed = time.monotonic() - start

            assert result == ("https://pixeldrain.com/api/file/abc123", {}), result
            assert elapsed < 0.1, (
                f"Pixeldrain esperó el lock ({elapsed:.3f}s) — no debería usar el lock"
            )
        finally:
            api._resolution_lock.release()
