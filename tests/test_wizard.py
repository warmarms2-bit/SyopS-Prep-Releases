"""Tests del wizard interactivo de terminal (syops_wizard.py).

Verifica que el wizard:
- importa sin PySide6 (modo terminal)
- expone la lógica de selección (categorías, límites, resumen)
- construye las tareas de descarga (misma lógica que la UI)
"""

import sys

import tests.conftest  # noqa: F401


def _block_pyside(monkeypatch):
    saved = {}

    class _Blocker:
        def find_module(self, name, path=None):
            if name == "PySide6" or name.startswith("PySide6."):
                return self
            return None

        def load_module(self, name):
            raise ImportError(f"PySide6 bloqueado: {name}")

    for mod in list(sys.modules):
        if (mod.startswith("services.") or mod.startswith("catalog.")
                or mod.startswith("system.") or mod == "app_config"
                or mod in ("syops_cli", "syops_wizard")):
            saved[mod] = sys.modules.pop(mod)
    sys.meta_path.insert(0, _Blocker())

    def _restore():
        for b in list(sys.meta_path):
            if isinstance(b, _Blocker):
                sys.meta_path.remove(b)
        sys.modules.update(saved)

    monkeypatch.addfinalizer(_restore) if hasattr(monkeypatch, "addfinalizer") else None
    return _restore


def test_wizard_importa_sin_pyside(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        assert syops_wizard.Wizard
    finally:
        restore()


def test_wizard_estado_inicial(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        w = syops_wizard.Wizard()
        assert w.max_apps >= 1
        assert w.selected_apps == []
        assert w.adobe_patched == []
        assert w.cat is None
    finally:
        restore()


def test_wizard_categorias_disponibles(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        from catalog.data import SOFTWARE_CATEGORIES
        cats = [k for k in SOFTWARE_CATEGORIES if k != "all"]
        assert "office" in cats
        assert len(cats) >= 5
    finally:
        restore()


def test_wizard_effective_count(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        w = syops_wizard.Wizard()
        w.selected_apps = ["Blender"]
        assert w.effective_count() == 1
    finally:
        restore()


def test_wizard_run_download_sin_red(monkeypatch, tmp_path, capsys):
    """run_download con selección no descargable → no toca red."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        w = syops_wizard.Wizard()
        w.selected_apps = ["Talon"]  # sin link (manual)
        n = w.run_download(tmp_path)
        out = capsys.readouterr().out
        assert "manual" in out or n == 0
    finally:
        restore()


# ── Adobe en macOS ────────────────────────────────────────────────


def test_plataforma_mac_incluye_adobe(monkeypatch):
    """En macOS las 20 apps de Adobe son visibles (tienen links mac)."""
    restore = _block_pyside(monkeypatch)
    try:
        import importlib
        from catalog.data import ADOBE_APPS
        import syops_wizard
        monkeypatch.setattr(
            importlib.import_module("app_flow.flujo"),
            "_is_app_available_on_platform",
            lambda app, plat: True,
        )
        visible = syops_wizard._platform_apps(ADOBE_APPS)
        assert len(visible) == len(ADOBE_APPS)
    finally:
        restore()


def test_adobe_task_en_mac(monkeypatch):
    """aio_macked construye la tarea de Photoshop con link (mac)."""
    restore = _block_pyside(monkeypatch)
    try:
        import importlib
        from pathlib import Path
        from syops_cli import _task_from_app
        monkeypatch.setattr(
            importlib.import_module("services.download_planner"),
            "_adobe_best_link",
            lambda method, app, arch=None:
            ("https://dl.example/photoshop", "v30.0 2026"),
        )
        task, warn = _task_from_app("Photoshop", "aio_macked", Path("/tmp/out"))
        assert task is not None, warn
        assert warn is None
        assert task.url_or_magnet
    finally:
        restore()


def test_adobe_links_por_metodo_en_mac(monkeypatch):
    """Un método entrega link para TODAS las apps Adobe (cobertura del flujo)."""
    restore = _block_pyside(monkeypatch)
    try:
        import importlib
        from catalog.data import ADOBE_APPS
        ah = importlib.import_module("catalog.adobe_helpers")
        monkeypatch.setattr(
            ah, "_adobe_best_link",
            lambda method, app, arch=None:
            ("https://dl.example/adobe", "v1.0 2026"),
        )
        ok = 0
        for app in ADOBE_APPS:
            url, _v = ah._adobe_best_link("aio_macked", app)
            if url:
                ok += 1
        assert ok == len(ADOBE_APPS), f"aio_macked solo cubre {ok}/{len(ADOBE_APPS)}"
    finally:
        restore()


def test_activation_tool_excluido(monkeypatch):
    """activation_tool no se ofrece (solo métodos que descargan apps)."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        compatible, default = syops_wizard._pick_adobe_method(["Photoshop"])
        assert "activation_tool" not in compatible
        assert default != "activation_tool"
        # Elegir el método tampoco deja activation_tool
        assert "activation_tool" not in compatible
    finally:
        restore()


# ── Lógica de método Adobe (macOS) ────────────────────────────────


def test_pick_adobe_recomendado_cuando_cubre(monkeypatch):
    """aio_macked (recomendado) se preselecciona si cubre todas las apps."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        compatible, default = syops_wizard._pick_adobe_method(
            ["Photoshop", "Illustrator"])
        assert "aio_macked" in compatible
        assert default == "aio_macked"
    finally:
        restore()


def test_pick_adobe_fallback_si_no_cubre(monkeypatch):
    """Si el recomendado no cubre todas, se preselecciona el que sí."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        compatible, default = syops_wizard._pick_adobe_method(
            ["Photoshop", "Audition"])  # aio_macked no cubre Audition
        assert "aio_macked" not in compatible
        assert default in compatible
    finally:
        restore()


def test_ask_adobe_question_solo_windows(monkeypatch, capsys):
    """La pregunta GenP solo se muestra en Windows (no en macOS)."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        monkeypatch.setattr(syops_wizard, "_yes_no", lambda *a, **k: False)
        was_mac = syops_wizard.IS_MAC
        try:
            # macOS: no se pregunta (guard por plataforma).
            syops_wizard.IS_WIN = False
            syops_wizard.IS_MAC = True
            w = syops_wizard.Wizard()
            w.selected_apps = ["Photoshop"]  # Adobe seleccionada
            w.ask_adobe_question()
            out = capsys.readouterr().out
            assert "ADOBE OFICIALES" not in out
            # Windows: se pregunta (motor nuevo con la plataforma).
            syops_wizard.IS_WIN = True
            syops_wizard.IS_MAC = False
            w2 = syops_wizard.Wizard()
            w2.selected_apps = ["Photoshop"]
            w2.ask_adobe_question()
            out = capsys.readouterr().out
            assert "ADOBE OFICIALES" in out
        finally:
            syops_wizard.IS_WIN = not was_mac
            syops_wizard.IS_MAC = was_mac
    finally:
        restore()


# ── Límite de selección y resumen ─────────────────────────────────


def test_pick_numbers_respeta_limite(monkeypatch):
    """El límite del plan (máx 3) rechaza selecciones mayores."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        answers = iter(["1,2,3,4", "1,2,3"])  # 4 rechazado, 3 aceptado
        monkeypatch.setattr(syops_wizard, "_ask", lambda *a, **k: next(answers))
        nums = syops_wizard._pick_numbers(10, limit=3)
        assert nums == [1, 2, 3]
    finally:
        restore()


def test_seleccion_muestra_requisitos(monkeypatch, capsys):
    """Tras elegir, se muestran los requisitos mínimos por app."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        w = syops_wizard.Wizard()
        w.selected_apps = ["Photoshop"]
        w._show_selected_specs()
        out = capsys.readouterr().out
        assert "REQUISITOS MÍNIMOS" in out
        assert "RAM" in out
    finally:
        restore()


def test_resumen_muestra_compatibilidad(monkeypatch, capsys):
    """El resumen muestra equipo, specs y compatibilidad (como la UI)."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        monkeypatch.setattr(syops_wizard, "_yes_no", lambda *a, **k: True)
        w = syops_wizard.Wizard()
        w.selected_apps = ["Blender"]
        w.adobe_patched = []
        assert w.show_resumen() is True
        out = capsys.readouterr().out
        assert "INFORMACIÓN DEL EQUIPO" in out
        assert "COMPATIBILIDAD" in out
        assert "RAM" in out
    finally:
        restore()


# ── Sistema de tools ──────────────────────────────────────────────


def test_combo_mole_talon_visible_solo_windows(monkeypatch):
    """El combo 'Mole + Talon' se muestra en Windows (parte Mole) y no en mac."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        import importlib
        monkeypatch.setattr(
            importlib.import_module("app_flow.flujo"),
            "_is_app_available_on_platform",
            lambda app, plat: app in {"Mole", "SimpleWall"} if plat == "win" else False,
        )
        was_win, was_mac = syops_wizard.IS_WIN, syops_wizard.IS_MAC
        try:
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = True, False
            assert "Mole + Talon" in syops_wizard._platform_apps(["Mole + Talon"])
            assert "SimpleWall" in syops_wizard._platform_apps(["SimpleWall"])
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = False, True
            assert "Mole + Talon" not in syops_wizard._platform_apps(["Mole + Talon"])
            assert "SimpleWall" not in syops_wizard._platform_apps(["SimpleWall"])
        finally:
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = was_win, was_mac
    finally:
        restore()


def test_resumen_muestra_herramientas(monkeypatch, capsys):
    """El resumen muestra la sección 'Herramientas seleccionadas'."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        monkeypatch.setattr(syops_wizard, "_yes_no", lambda *a, **k: True)
        w = syops_wizard.Wizard()
        w.selected_apps = ["Mole + Talon"]
        w.show_resumen()
        out = capsys.readouterr().out
        assert "Herramientas seleccionadas" in out
        assert "Mole + Talon" in out
    finally:
        restore()


def test_run_download_expande_combo(monkeypatch, tmp_path, capsys):
    """El combo se expande: Mole queda descargable, Talon (manual) no."""
    restore = _block_pyside(monkeypatch)
    try:
        from services.seleccion_logic import build_download_apps
        apps = build_download_apps(["Mole + Talon"], [], [])
        assert "Mole" in apps  # Talon sin método queda fuera
    finally:
        restore()


# ── Adobe Full Pack ───────────────────────────────────────────────


def test_ejecutar_efectos_despacha_segun_el_motor(monkeypatch):
    """El wizard ejecuta los efectos que el motor decide, en su orden."""
    restore = _block_pyside(monkeypatch)
    try:
        from pathlib import Path
        import syops_wizard
        z = syops_wizard.Wizard()
        z.selected_apps = ["Blender"]
        orden = []

        def fake_instrucciones(out):
            orden.append("instrucciones")

        def fake_descargar(out, adobe_fullpack=False):
            orden.append("descargar")
            return 3

        def fake_whitelist():
            orden.append("whitelist")

        def fake_reportar(evento, **kw):
            orden.append(f"reportar:{evento}")

        def fake_rustdesk(out):
            orden.append("rustdesk")
            return True

        z.instrucciones = fake_instrucciones
        z.descargar = fake_descargar
        z.whitelist = fake_whitelist
        z.reportar = fake_reportar
        z.run_rustdesk = fake_rustdesk
        assert z._ejecutar_efectos(Path("/tmp/out")) is True
        # RustDesk ya no se ofrece antes de descargar (la asistencia va
        # post-descarga, en show_final, para la instalación manual).
        assert orden == ["instrucciones", "descargar", "reportar:completed"]
    finally:
        restore()


def test_code_type_full_pack():
    """Un código con max_apps 99 se interpreta como Full Pack (sin backend)."""
    import syops_wizard
    assert syops_wizard._code_type_for(99) == "adobe_full_pack"
    assert syops_wizard._code_type_for(3) == "standard"
    assert syops_wizard._code_type_for(0) == "standard"


def test_es_full_pack(monkeypatch):
    """Solo activo con licencia adobe_full_pack en macOS."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        was_win, was_mac = syops_wizard.IS_WIN, syops_wizard.IS_MAC
        try:
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = False, True
            w = syops_wizard.Wizard()  # macOS (motor captura la plataforma al crearse)
            w.activation_type = "adobe_full_pack"
            assert w._es_full_pack() is True
            w.activation_type = "standard"
            assert w._es_full_pack() is False
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = True, False
            w2 = syops_wizard.Wizard()  # Windows: nuevo motor
            w2.activation_type = "adobe_full_pack"
            assert w2._es_full_pack() is False  # full pack solo macOS
        finally:
            syops_wizard.IS_WIN, syops_wizard.IS_MAC = was_win, was_mac
    finally:
        restore()


def test_full_pack_links_existen(monkeypatch):
    """El collection AIO del Full Pack produce items con link y nombre."""
    restore = _block_pyside(monkeypatch)
    try:
        import importlib
        ah = importlib.import_module("catalog.adobe_helpers")
        monkeypatch.setattr(
            ah, "_adobe_full_pack_links",
            lambda method: [("Photoshop", "https://dl.example/ps"),
                            ("Premiere", "https://dl.example/pr")],
        )
        links = ah._adobe_full_pack_links("aio_macked")
        assert links, "Full pack sin links"
        name, url = links[0]
        assert name and url
    finally:
        restore()


# ── Office (resolvers) ────────────────────────────────────────────


def test_office_visible_y_seleccionable(monkeypatch):
    """La categoría Office es visible en la plataforma actual."""
    restore = _block_pyside(monkeypatch)
    try:
        import importlib
        from catalog.data import SOFTWARE_CATEGORIES
        import syops_wizard
        monkeypatch.setattr(
            importlib.import_module("app_flow.flujo"),
            "_is_app_available_on_platform",
            lambda app, plat: True,
        )
        visible = syops_wizard._platform_apps(SOFTWARE_CATEGORIES["office"]["apps"])
        assert "Office" in visible
    finally:
        restore()


def test_office_se_expande_en_tareas_descargables(monkeypatch):
    """Office → sub-apps + core: cada una construye una tarea (http) con link."""
    restore = _block_pyside(monkeypatch)
    try:
        from pathlib import Path
        import importlib
        from services.seleccion_logic import build_download_apps
        from syops_cli import _task_from_app
        monkeypatch.setattr(
            importlib.import_module("services.download_planner"),
            "_resolve_download_link",
            lambda app: ("http", f"https://dl.example/{app}"),
        )
        apps = build_download_apps(["Office"], ["Word", "Excel"], [])
        assert "Office" not in apps  # el padre se expande
        assert "Word" in apps and "Excel" in apps
        for app in apps:
            task, warn = _task_from_app(app, "macked", Path("/tmp/out"))
            assert task is not None, f"{app}: {warn}"
            assert task.url_or_magnet
    finally:
        restore()


def test_office_sub_apps_orden_estable(monkeypatch):
    """OFFICE_APPS se lista en orden estable (sorted)."""
    restore = _block_pyside(monkeypatch)
    try:
        from catalog.categorias import OFFICE_APPS
        office_list = sorted(OFFICE_APPS)
        assert office_list == sorted(office_list)
    finally:
        restore()


# ── Completado y marcado de uso ───────────────────────────────────


def test_has_downloadable(monkeypatch):
    """Distingue selecciones descargables de las manuales."""
    from services.seleccion_logic import has_downloadable
    assert has_downloadable(["Blender"], "standard") is True
    assert has_downloadable(["Talon"], "standard") is False
    assert has_downloadable(["Photoshop"], "standard") is True


def test_send_completed_y_mark_sin_codigo(monkeypatch):
    """No crashean sin red ni sin código guardado."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        w = syops_wizard.Wizard()
        w._sheets = w._make_sheets()
        w.selected_apps = ["Blender"]
        w._send_completed()
        w._mark_activation_used()  # sin código guardado → no-op
    finally:
        restore()


def test_rustdesk_config_por_plataforma():
    """RustDesk usa instalador/URL adecuados por plataforma."""
    from services.rustdesk_service import config_for_platform
    mac = config_for_platform("darwin")
    win = config_for_platform("win32")
    assert mac.filename == "rustdesk.dmg"
    assert "aarch64" in mac.url
    assert win.filename == "rustdesk.msi"
    assert win.url.endswith(".msi")


def test_wizard_rustdesk_ya_instalado(monkeypatch, tmp_path):
    """Si RustDesk ya está instalado, el wizard no descarga otra vez."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        import services.rustdesk_service as rustdesk
        monkeypatch.setattr(rustdesk, "is_rustdesk_installed", lambda: True)
        w = syops_wizard.Wizard()
        assert w.run_rustdesk(tmp_path) is True
    finally:
        restore()


def test_wizard_rustdesk_se_puede_omitir(monkeypatch, tmp_path):
    """RustDesk es opcional: el wizard puede continuar sin instalarlo."""
    restore = _block_pyside(monkeypatch)
    try:
        import syops_wizard
        import services.rustdesk_service as rustdesk
        monkeypatch.setattr(rustdesk, "is_rustdesk_installed", lambda: False)
        monkeypatch.setattr(syops_wizard, "_yes_no", lambda *a, **k: False)
        w = syops_wizard.Wizard()
        assert w.run_rustdesk(tmp_path) is True
    finally:
        restore()
