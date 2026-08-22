"""Tests del esqueleto del flujo (app_flow/).

Verifica que la lógica de decisión (reglas + transiciones) es la misma
que usa la UI, agnóstica de presentación. Al migrar la UI a este esqueleto,
estos tests pasan a cubrir ambas vistas.
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
                or mod in ("app_flow", "app_flow.flujo")):
            saved[mod] = sys.modules.pop(mod)
    sys.meta_path.insert(0, _Blocker())

    def _restore():
        for b in list(sys.meta_path):
            if isinstance(b, _Blocker):
                sys.meta_path.remove(b)
        sys.modules.update(saved)

    return _restore


# ── Reglas puras ──────────────────────────────────────────────────


def test_platform_apps_filtra_por_so(monkeypatch):
    """Las apps sin link para el SO se ocultan; Office y combos se expanden."""
    restore = _block_pyside(monkeypatch)
    try:
        from app_flow import platform_apps, flujo
        from catalog.data import SOFTWARE_CATEGORIES
        from catalog.categorias import OFFICE_APPS, OFFICE_CORE_APPS
        # El catálogo local no lleva URLs (viven en el Sheet); inyectamos
        # disponibilidad sintética para probar la regla de filtrado:
        # Office disponible en ambas, SimpleWall/Mole/Talon solo en Windows.
        mac_core = set(OFFICE_APPS) | set(OFFICE_CORE_APPS)
        win_only = {"SimpleWall", "Mole", "Talon"}
        monkeypatch.setattr(
            flujo, "_is_app_available_on_platform",
            lambda app, plat: app in mac_core if plat == "mac"
                              else app in (win_only | mac_core),
        )
        key = "graphic_design" if "graphic_design" in SOFTWARE_CATEGORIES else "design"
        platform_apps(SOFTWARE_CATEGORIES[key]["apps"], True, False)
        win_apps = platform_apps(["SimpleWall", "Mole + Talon"], False, True)
        assert "SimpleWall" in win_apps          # solo Windows
        mac_util = platform_apps(["SimpleWall"], True, False)
        assert "SimpleWall" not in mac_util      # oculta en mac
        mac_opt = platform_apps(["Mole + Talon"], True, False)
        assert "Mole + Talon" not in mac_opt     # combo solo Windows
        assert "Mole + Talon" in platform_apps(["Mole + Talon"], False, True)
        office_mac = platform_apps(["Office"], True, False)
        assert "Office" in office_mac            # padre visible si sub-apps mac
    finally:
        restore()


def test_metodos_compatibles_cubren_todas(monkeypatch):
    """Solo métodos que cubren TODAS las apps; activation_tool excluido."""
    restore = _block_pyside(monkeypatch)
    try:
        from app_flow import metodos_compatibles
        assert "activation_tool" not in metodos_compatibles(["Photoshop"])
        assert "aio_macked" in metodos_compatibles(["Photoshop", "Illustrator"])
        assert "aio_macked" not in metodos_compatibles(["Photoshop", "Audition"])
    finally:
        restore()


def test_preseleccionar_metodo(monkeypatch):
    """Preselección: aio_macked si compatible; si no, el único/primero."""
    restore = _block_pyside(monkeypatch)
    try:
        from app_flow import preseleccionar_metodo
        compat, default = preseleccionar_metodo(["Photoshop", "Illustrator"])
        assert default == "aio_macked"
        compat, default = preseleccionar_metodo(["Photoshop", "Audition"])
        assert "aio_macked" not in compat
        assert default in compat
    finally:
        restore()


# ── FlujoMotor ────────────────────────────────────────────────────


def _motor(mac=True, win=False):
    from app_flow import FlujoMotor
    return FlujoMotor("C1", "H1", mac, win)


def test_motor_agregar_limite_y_dedup(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor()
        m.agregar_apps(["Photoshop", "Illustrator", "Blender"])  # 3 = límite
        assert m.state.seleccion == ["Photoshop", "Illustrator", "Blender"]
        assert not m.puede_agregar()
        m.agregar_apps(["Photoshop", "ZBrush"])  # duplicado + excede
        assert m.state.seleccion == ["Photoshop", "Illustrator", "Blender"]
    finally:
        restore()


def test_motor_remover_apps_deseleccionar(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor()
        m.agregar_apps(["Photoshop", "Illustrator", "Blender"])
        removidos = m.remover_apps(["Illustrator", "Sketch"])
        assert removidos == ["Illustrator"]
        assert m.state.seleccion == ["Photoshop", "Blender"]
        assert m.puede_agregar()
        m.agregar_apps(["ZBrush"])
        assert m.state.seleccion == ["Photoshop", "Blender", "ZBrush"]
    finally:
        restore()


def test_motor_remover_apps_limpia_office_y_adobe(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor()
        m.agregar_apps(["Office", "Photoshop"])
        m.elegir_office(["Word", "Excel"])
        m.marcar_adobe_patched(["Photoshop"])
        m.remover_apps(["Office", "Photoshop"])
        assert m.state.seleccion == []
        assert m.state.office_sub == []
        assert m.state.adobe_patched == []
    finally:
        restore()


def test_motor_efectivo_conteo_credito_adobe(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        from app_flow import FlujoMotor
        from catalog.adobe_helpers import _adobe_count_for_limit
        m = FlujoMotor("C1", "H1", True, False)
        m.set_activacion(True, 3, "standard")
        apps = ["Photoshop", "Illustrator", "Blender"]
        m.agregar_apps(apps)
        non_adobe = [a for a in apps if a not in ("Photoshop", "Illustrator")]
        esperado = len(non_adobe) + _adobe_count_for_limit(apps)
        assert m.efectivo_conteo() == esperado == 3
    finally:
        restore()


def test_motor_pregunta_adobe_solo_windows(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor(mac=False, win=True)
        m.agregar_apps(["Photoshop"])
        assert m.pregunta_adobe_pendiente() is True
        m2 = _motor(mac=True, win=False)
        m2.agregar_apps(["Photoshop"])
        assert m2.pregunta_adobe_pendiente() is False
    finally:
        restore()


def test_motor_es_full_pack_solo_mac(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor(mac=True, win=False)
        m.set_activacion(True, 99, "adobe_full_pack")
        assert m.es_full_pack is True
        mw = _motor(mac=False, win=True)
        mw.set_activacion(True, 99, "adobe_full_pack")
        assert mw.es_full_pack is False
    finally:
        restore()


def test_motor_siguiente_transiciones(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        from app_flow import Etapa, FlujoMotor
        # con Office → OFFICE; sin adobe → RESUMEN
        m = FlujoMotor("C1", "H1", True, False)
        m.agregar_apps(["Office"])
        m.en_etapa(Etapa.SELECCION)
        assert m.siguiente() == Etapa.OFFICE
        # adobe en mac → ADOBE_METHOD
        m2 = FlujoMotor("C1", "H1", True, False)
        m2.agregar_apps(["Photoshop"])
        m2.en_etapa(Etapa.SELECCION)
        assert m2.siguiente() == Etapa.ADOBE_METHOD
        # sin office ni adobe → RESUMEN
        m3 = FlujoMotor("C1", "H1", True, False)
        m3.agregar_apps(["Blender"])
        m3.en_etapa(Etapa.SELECCION)
        assert m3.siguiente() == Etapa.RESUMEN
    finally:
        restore()


def test_motor_tiene_descargable(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        m = _motor()
        m.agregar_apps(["Blender"])
        assert m.tiene_descargable() is True
        m2 = _motor()
        m2.agregar_apps(["Talon"])  # manual, sin link
        assert m2.tiene_descargable() is False
    finally:
        restore()


def test_motor_efectos_necesarios(monkeypatch):
    restore = _block_pyside(monkeypatch)
    try:
        # Con descarga: instrucciones + descargar (+ whitelist solo Windows).
        m = _motor(mac=True, win=False)
        m.agregar_apps(["Blender"])
        assert m.efectos_necesarios() == ["instrucciones", "descargar", "reportar"]
        mw = _motor(mac=False, win=True)
        mw.agregar_apps(["Blender"])
        assert mw.efectos_necesarios() == ["instrucciones", "descargar", "whitelist", "reportar"]
        # Sin nada descargable: solo reportar el cierre.
        m2 = _motor()
        m2.agregar_apps(["Talon"])
        assert m2.efectos_necesarios() == ["reportar"]
    finally:
        restore()
