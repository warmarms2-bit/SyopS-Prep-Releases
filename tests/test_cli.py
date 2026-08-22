"""Tests del CLI de terminal (dominio puro, sin UI/Qt).

Verifica que syops_cli.py funciona como interfaz de terminal:
- importa sin PySide6 (bloqueado)
- comandos de información/catálogo producen salida
- construcción de tareas de descarga (sin red)
"""

import sys

import tests.conftest  # noqa: F401


def _block_pyside(monkeypatch):
    """Bloquea PySide6 para forzar el modo sin Qt.

    Guarda el estado de sys.modules del dominio y lo restaura en el
    teardown, para no invalidar las clases que otros tests ya importaron
    (ej. DownloadEngine) — de lo contrario se duplican clases y fallan
    tests de otros archivos.
    """
    saved = {}

    class _Blocker:
        def find_module(self, name, path=None):
            if name == "PySide6" or name.startswith("PySide6."):
                return self
            return None

        def load_module(self, name):
            raise ImportError(f"PySide6 bloqueado: {name}")

    # Limpiar módulos del dominio ya importados (para re-import limpio).
    for mod in list(sys.modules):
        if (mod.startswith("services.") or mod.startswith("catalog.")
                or mod.startswith("system.") or mod == "app_config"
                or mod == "syops_cli"):
            saved[mod] = sys.modules.pop(mod)
    sys.meta_path.insert(0, _Blocker())

    def _restore():
        for b in list(sys.meta_path):
            if isinstance(b, _Blocker):
                sys.meta_path.remove(b)
        sys.modules.update(saved)

    return _restore


def test_cli_importa_sin_pyside(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        assert syops_cli.main  # invocable
    finally:
        restore()


def test_cmd_info(capsys, monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        syops_cli.cmd_info(_Args())
        out = capsys.readouterr().out
        assert "SyopS Prep v" in out
        assert "Cliente ID" in out
        assert "Hardware ID" in out
    finally:
        restore()


def test_cmd_categorias(capsys, monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        syops_cli.cmd_categorias(_Args())
        out = capsys.readouterr().out
        assert "Photoshop" in out  # alguna app del catálogo
    finally:
        restore()


def test_cmd_metodos_desconocido(capsys, monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        syops_cli.cmd_metodos(_Args(app="NoExisteApp"))
        out = capsys.readouterr().out
        assert "no está en el catálogo" in out
    finally:
        restore()


def test_cmd_status(capsys, monkeypatch, tmp_path):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        monkeypatch.setattr(syops_cli, "SYOPS_DIR", tmp_path)  # estado vacío → no activado
        syops_cli.cmd_status(_Args())
        out = capsys.readouterr().out
        assert "Activado" in out
    finally:
        restore()


def test_task_from_app_http(monkeypatch):
    import importlib
    from syops_cli import _task_from_app
    from pathlib import Path

    # El catálogo local no lleva URLs (viven en el Sheet); inyectamos una
    # falsa para probar que Blender (http directo) produce tarea sin resolver.
    monkeypatch.setattr(
        importlib.import_module("services.download_planner"),
        "_resolve_download_link",
        lambda app: ("http", f"https://dl.example/{app}"),
    )
    task, warn = _task_from_app("Blender", "macked", Path("/tmp/out"))
    assert task is not None
    assert warn is None
    assert task.method == "http"
    assert task.url_or_magnet


def test_task_from_app_desconocida(monkeypatch):
    from syops_cli import _task_from_app
    from pathlib import Path

    task, warn = _task_from_app("AppNoExiste", "macked", Path("/tmp/out"))
    assert task is None
    assert "sin link" in warn or "manual" in warn


def test_descargar_sin_nada(capsys, monkeypatch):
    """Selección vacía → aviso, sin tocar red."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_cli
        syops_cli.cmd_descargar(_Args(apps=["AppNoExiste"], office=None,
                                      adobe_metodo=None, dir=None))
        out = capsys.readouterr().out
        assert "Nada descargable" in out
    finally:
        restore()


class _Args:
    def __init__(self, **kw):
        self.app = kw.get("app", None)
        self.apps = kw.get("apps", [])
        self.codigo = kw.get("codigo", "")
        self.office = kw.get("office", None)
        self.adobe_metodo = kw.get("adobe_metodo", None)
        self.dir = kw.get("dir", None)
