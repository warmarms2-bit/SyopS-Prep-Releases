"""
Tests de regresión para el fix de resume en download_engine.py.

Cubre _single_download_sync y el "already complete" path de
_download_http_single. Mockeamos urllib.request.urlopen para no hacer
requests reales; los archivos temporales se crean en tmp_path (fixture
de pytest).

Reglas que estos tests blindan:
  - El tamaño del archivo (resume_from) y el header Content-Range del
    servidor son las fuentes de verdad del tamaño total.
  - total_hint solo se usa como fallback cuando el servidor no provee
    Content-Range.
  - Si el servidor ignora el header Range y devuelve 200 a un request
    con Range, NO se appenda contenido sobre el archivo parcial: se
    reinicia la descarga desde cero (unlink + wb).
  - Cuando el archivo en disco ya es completo respecto a total_hint
    pero los tamaños no coinciden, la validación usa el tamaño real
    en disco y se loguea un warning (no falla por la discrepancia).
"""

import asyncio
import urllib.request

import pytest


# ── Helpers ────────────────────────────────────────────────────────


class FakeResponse:
    """Response fake con la API mínima que usa _single_download_sync.

    Implementa el context manager (with ... as resp) y `read(n)`.
    Devuelve `self._body` en el primer read y b"" después, lo que
    cierra el loop de descarga en _single_download_sync.
    """

    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self._read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=-1):
        if self._read_count == 0 and self._body:
            self._read_count += 1
            return self._body
        return b""


@pytest.fixture
def stub_urlopen(monkeypatch):
    """Reemplaza urllib.request.urlopen por una función configurable.

    Uso:
        stub_urlopen.set(FakeResponse(status=200, headers={...}, body=b"..."))
        engine._single_download_sync(...)  # usa el response configurado
    """
    state = {"response": None}

    def _fake_urlopen(req, **kwargs):
        return state["response"]

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    # Exponemos set() para que los tests configuren el response sin
    # depender de un atributo mutable de un SimpleNamespace.
    class _Stub:
        def set(self, response):
            state["response"] = response

        @property
        def response(self):
            return state["response"]

    return _Stub()


@pytest.fixture
def silent_progress(monkeypatch):
    """Silencia _emit_progress para que los tests no impriman progreso."""

    def _noop(self, *args, **kwargs):
        pass

    # Patch sobre la clase; cualquier instancia ve el noop.
    monkeypatch.setattr("services.download_engine.DownloadEngine._emit_progress", _noop)
    monkeypatch.setattr("services.download_engine.DownloadEngine._emit_completed", _noop)


# Importamos download_engine SOLO después de que conftest.py haya
# mockeado PySide6. Eso lo garantiza el orden de carga de pytest
# (conftest.py se procesa antes que los test_*.py).
from services.download_engine import DownloadEngine  # noqa: E402


# ── Tests ──────────────────────────────────────────────────────────


class TestSingleDownloadSync:
    """Tests para _single_download_sync (la función sync que hace el I/O)."""

    def test_server_returns_200_to_range_request_restarts_from_scratch(
        self, tmp_path, stub_urlopen, silent_progress, caplog
    ):
        """Caso 1: server ignora Range, devuelve 200 con el archivo completo.

        Debe detectar no-206, hacer unlink del temp, resetear resume_from=0,
        abrir en 'wb' (no 'ab') y NO concatenar contenido nuevo sobre el viejo.
        """
        import logging
        caplog.set_level(logging.WARNING, logger="services.download_engine")

        # Arrange: temp existente con 100 bytes previos
        temp = tmp_path / "partial.tmp"
        temp.write_bytes(b"X" * 100)

        # Server devuelve 200 (no 206) con archivo completo de 200 bytes
        stub_urlopen.set(FakeResponse(
            status=200,
            headers={"content-length": "200"},
            body=b"Z" * 200,
        ))

        engine = DownloadEngine()
        headers = {"Range": "bytes=100-"}

        # Act
        downloaded, total = engine._single_download_sync(
            "TestApp", "http://example.com/file", headers, tmp_path / "dest",
            temp, resume_from=100, total_hint=1000,
        )

        # Assert: contenido del archivo en disco
        assert temp.read_bytes() == b"Z" * 200, (
            f"Esperaba 200 bytes de 'Z' (modo wb). "
            f"Encontré {len(temp.read_bytes())} bytes — el fix NO evitó el append."
        )
        # El archivo NO debe contener los 100 bytes viejos de 'X'
        assert b"X" not in temp.read_bytes(), (
            "Quedaron bytes del archivo viejo — el unlink() no ocurrió."
        )

        # Valores devueltos
        assert downloaded == 200, "downloaded debe ser 200 (bytes recibidos del body)"
        assert total == 200, (
            f"total debe ser 200 (content-length del 200 response), no {total}. "
            "Si devolvió 1000 es porque sigue usando total_hint."
        )

        # El warning de restart debe estar en el logger
        assert "restarting download from scratch" in caplog.text, (
            f"Falta el warning de restart. Log capturado: {caplog.text!r}"
        )

    def test_content_range_with_asterisk_total_falls_back_to_hint(
        self, tmp_path, stub_urlopen, silent_progress, caplog
    ):
        """Caso 2: Content-Range 'bytes 100-199/*' (total desconocido).

        El regex de parseo no debe crashear; debe caer al fallback de
        total_hint y loguear el warning correspondiente.
        """
        import logging
        caplog.set_level(logging.WARNING, logger="services.download_engine")

        # Arrange: temp con 100 bytes, server devuelve los siguientes 100
        temp = tmp_path / "partial.tmp"
        temp.write_bytes(b"X" * 100)

        stub_urlopen.set(FakeResponse(
            status=206,
            headers={
                "content-length": "100",
                "content-range": "bytes 100-199/*",  # asterisco, no total
            },
            body=b"Y" * 100,
        ))

        engine = DownloadEngine()
        headers = {"Range": "bytes=100-"}

        # Act
        downloaded, total = engine._single_download_sync(
            "TestApp", "http://example.com/file", headers, tmp_path / "dest",
            temp, resume_from=100, total_hint=200,
        )

        # Assert
        assert downloaded == 200, "downloaded = 100 (previo) + 100 (recibidos)"
        assert total == 200, (
            f"total debe caer al fallback total_hint=200, no {total}"
        )
        # Archivo en disco: 100 X + 100 Y = 200 bytes
        content = temp.read_bytes()
        assert content == b"X" * 100 + b"Y" * 100, (
            f"Concatenación incorrecta. Len={len(content)}, "
            f"primeros bytes={content[:10]!r}, últimos={content[-10:]!r}"
        )

        # Warning de Content-Range con asterisco
        assert "206 without Content-Range total" in caplog.text, (
            f"Falta warning de 206 sin total. Log capturado: {caplog.text!r}"
        )

    def test_206_without_content_range_and_zero_hint_no_crash(
        self, tmp_path, stub_urlopen, silent_progress
    ):
        """Caso 3: 206 sin Content-Range y total_hint=0.

        No debe haber división por cero, comparación con None, ni
        excepción. La descarga continúa byte a byte y downloaded refleja
        los bytes reales. El progreso no tiene porcentaje (total=0).
        """
        # Arrange
        temp = tmp_path / "partial.tmp"
        temp.write_bytes(b"X" * 50)

        stub_urlopen.set(FakeResponse(
            status=206,
            headers={
                "content-length": "50",
                # SIN content-range header
            },
            body=b"Y" * 50,
        ))

        engine = DownloadEngine()
        headers = {"Range": "bytes=50-"}

        # Act & Assert: no debe lanzar excepción
        downloaded, total = engine._single_download_sync(
            "TestApp", "http://example.com/file", headers, tmp_path / "dest",
            temp, resume_from=50, total_hint=0,
        )

        # Sin división por cero, total queda en fallback (0)
        assert total == 0, f"total debe ser 0 (fallback). Encontrado: {total}"
        assert downloaded == 100, f"downloaded debe ser 100. Encontrado: {downloaded}"

        # El archivo se escribió correctamente en modo append
        content = temp.read_bytes()
        assert content == b"X" * 50 + b"Y" * 50, (
            f"Archivo mal escrito. Len={len(content)}"
        )

    def test_206_with_matching_content_range_and_hint_no_warning(
        self, tmp_path, stub_urlopen, silent_progress, capsys
    ):
        """Caso 5 (feliz): 206 con Content-Range total=1000 y total_hint=1000.

        No debe loguearse warning de discrepancia. total debe ser 1000
        extraído del Content-Range.
        """
        # Arrange
        temp = tmp_path / "partial.tmp"
        temp.write_bytes(b"X" * 500)

        stub_urlopen.set(FakeResponse(
            status=206,
            headers={
                "content-length": "500",
                "content-range": "bytes 500-999/1000",
            },
            body=b"Y" * 500,
        ))

        engine = DownloadEngine()
        headers = {"Range": "bytes=500-"}

        # Act
        downloaded, total = engine._single_download_sync(
            "TestApp", "http://example.com/file", headers, tmp_path / "dest",
            temp, resume_from=500, total_hint=1000,
        )

        # Assert
        assert downloaded == 1000
        assert total == 1000, (
            f"total debe ser 1000 del Content-Range, no {total}"
        )
        # Archivo final: 1000 bytes
        assert temp.stat().st_size == 1000
        assert temp.read_bytes() == b"X" * 500 + b"Y" * 500

        # NO debe haber warning de discrepancia
        captured = capsys.readouterr()
        assert "differs from total_hint" not in captured.out, (
            f"Apareció warning de discrepancia cuando coinciden. "
            f"Output: {captured.out!r}"
        )


class TestAlreadyCompletePath:
    """Tests para el path 'already complete' de _download_http_single."""

    def test_already_complete_with_outdated_hint_uses_actual_size(
        self, tmp_path, silent_progress, caplog
    ):
        """Caso 4: archivo en disco YA completo (>= total_hint) pero con
        total_hint desactualizado.

        Condición del path: resume_from >= total_hint (archivo ya es
        completo respecto al hint). El hint está mal: subestima el
        tamaño real. El fix debe:
          - Loguear warning de discrepancia.
          - Usar resume_from (tamaño real en disco) como expected_size
            al validar, NO total_hint.
          - NO fallar la descarga por la discrepancia.
        """
        import logging
        caplog.set_level(logging.WARNING, logger="services.download_engine")

        # Arrange: temp con 1000 bytes reales, total_hint dice 950
        # (resume_from=1000 >= total_hint=950 → entra al "already complete")
        temp = tmp_path / "partial.tmp"
        temp.write_bytes(b"X" * 1000)

        # Capturamos signals para verificar que la tarea se completó OK
        completed_calls = []

        def _capture_completed(self, name, success, size):
            completed_calls.append((name, success, size))

        from services.download_engine import DownloadEngine as _DE
        _DE._emit_completed = _capture_completed

        # _emit_progress sigue silent_progress (noop via fixture)
        engine = DownloadEngine()
        engine._emit_progress = lambda *a, **kw: None  # redundante con fixture, por claridad

        # Act: _download_http_single es async
        asyncio.run(
            engine._download_http_single(
                "TestApp",
                "http://example.com/file",
                dest=tmp_path / "dest.bin",
                temp=temp,
                total_hint=950,
            )
        )

        # Assert: NO se retornó ningún valor (la función no retorna)
        # Lo que importa es el side-effect del signal `completed`
        assert len(completed_calls) == 1, (
            f"Esperaba 1 emit de completed, hubo {len(completed_calls)}: {completed_calls}"
        )
        name, success, size = completed_calls[0]
        assert success is True, "La tarea debe completarse con éxito"
        assert size == 1000, f"size debe ser 1000 (tamaño real), no {size}"
        assert name == "TestApp"

        # El archivo destino debe existir y tener 1000 bytes
        dest = tmp_path / "dest.bin"
        assert dest.exists(), "El archivo destino debe existir"
        assert dest.stat().st_size == 1000, (
            f"Dest debe tener 1000 bytes, tiene {dest.stat().st_size}"
        )

        # El temp debe haber sido movido a dest
        assert not temp.exists(), "El temp debe haber sido renombrado a dest"

        # Warning de discrepancia debe estar en el logger
        assert "actual file size (1000) differs from total_hint (950)" in caplog.text, (
            f"Falta warning de discrepancia. Log capturado: {caplog.text!r}"
        )
