"""
conftest.py para tests de SyopS Prep.

Mockea PySide6 y qfluentwidgets ANTES de que se cargue cualquier módulo
de la app (syops_prep.py, download_engine.py, download_manager.py). La
app usa Qt para la UI, pero los tests corren headless sin display server.

Los stubs son flexibles:
  - sirven como clases base (QWidget, QObject, QFrame, ...)
  - aceptan cualquier argumento sin efectos colaterales
  - permiten acceso a atributos a nivel de clase (QTimer.singleShot, ...)
    y a nivel de instancia (Qt.AlignCenter, ...)
Solo se ejercita código de UI al llamar métodos en runtime, no al importar,
así que los stubs alcanzan para que el import de la app no falle.
"""

import os
import sys
from types import SimpleNamespace

# Los tests corren offline (herméticos): el wizard no consulta el backend en
# pruebas; el catalogo servido se testea en test_server_catalog.py con mocks.
os.environ.setdefault("SYOPS_NO_CATALOG_FETCH", "1")


class _StubMeta(type):
    """Metaclass que permite acceso de atributo a nivel de clase
    (ej. QTimer.singleShot, QFontDatabase.addApplicationFont)."""

    def __getattr__(cls, name):
        return _Stub()


class _Stub(metaclass=_StubMeta):
    """Fake genérico de una clase Qt: usable como base, callable y namespace."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *args, **kwargs):
        return _Stub()


class _StubSignal:
    """Signal fake: connect/emit son no-ops."""

    def __init__(self, *args, **kwargs):
        self._args = args

    def connect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


def _qt_module(*names):
    ns = SimpleNamespace()
    for n in names:
        setattr(ns, n, _Stub)
    return ns


_qtcore = _qt_module(
    "Qt", "QObject", "QUrl", "QTimer", "QPropertyAnimation",
    "QEasingCurve", "QEvent", "QPoint", "QRect", "QSize",
)
_qtcore.Signal = _StubSignal

_qtgui = _qt_module(
    "QPainter", "QColor", "QLinearGradient", "QFont", "QPixmap", "QIcon",
    "QDesktopServices", "QFontDatabase", "QFontMetrics",
    "QPen", "QPalette",
)
_qtwidgets = _qt_module(
    "QApplication", "QWidget", "QVBoxLayout", "QHBoxLayout", "QGridLayout",
    "QLabel", "QPushButton", "QStackedWidget", "QFrame", "QScrollArea",
    "QGraphicsOpacityEffect", "QLineEdit", "QTextEdit", "QMessageBox",
    "QToolButton", "QDialog", "QSizePolicy", "QRadioButton", "QButtonGroup",
)
_qtmultimedia = _qt_module("QMediaPlayer", "QAudioOutput")
_qtmultimediawidgets = _qt_module("QVideoWidget")

_qfluentwidgets = _qt_module(
    "setThemeColor", "PrimaryPushButton", "PushButton", "ProgressBar",
    "InfoBar", "InfoBarPosition", "CheckBox", "RadioButton",
    "NavigationInterface", "NavigationWidget", "NavigationItemPosition",
    "SwitchButton", "FluentIcon", "Theme", "MessageBox", "Flyout",
    "TeachingTip", "ProgressRing", "CardWidget", "SimpleCardWidget",
    "InfoBadge", "SegmentedWidget", "SplashScreen", "FluentWindow",
    "setTheme", "IconWidget", "TitleLabel", "SubtitleLabel", "BodyLabel",
    "StrongBodyLabel", "CaptionLabel",
)

# Registrar ANTES de cualquier import de la app.
sys.modules.setdefault("PySide6", SimpleNamespace(
    QtCore=_qtcore, QtGui=_qtgui, QtWidgets=_qtwidgets,
    QtMultimedia=_qtmultimedia, QtMultimediaWidgets=_qtmultimediawidgets,
))
sys.modules.setdefault("PySide6.QtCore", _qtcore)
sys.modules.setdefault("PySide6.QtGui", _qtgui)
sys.modules.setdefault("PySide6.QtWidgets", _qtwidgets)
sys.modules.setdefault("PySide6.QtMultimedia", _qtmultimedia)
sys.modules.setdefault("PySide6.QtMultimediaWidgets", _qtmultimediawidgets)
sys.modules.setdefault("qfluentwidgets", _qfluentwidgets)
