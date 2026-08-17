"""Signals de Python puro compatibles con la API de Qt.

Reemplaza a ``PySide6.QtCore.Signal`` en los módulos de dominio
(services/) para que el núcleo de SyopS funcione SIN Qt (terminal, tests,
servicios). La API es la misma que usan los consumers:

  - ``connect(slot, type=None)``
  - ``disconnect(slot=None)``  (sin argumentos = desconectar todos)
  - ``emit(*args)``

Cuando Qt está disponible, los consumers pueden usar conexiones
``QueuedConnection`` reales (seguir con ``queued_kw()``); en un entorno
sin Qt la conexión es directa.

Uso (igual que antes)::

    class MiMotor:
        progress = Signal(str, int)

        def _notify(self, pct):
            self.progress.emit("x", pct)

    motor = MiMotor()
    motor.progress.connect(lambda n, p: print(p), **queued_kw())
"""


class Signal:
    """Emisor de eventos de Python con la misma API que las señales de Qt."""

    def __init__(self, *types):
        self._types = types
        self._slots = []

    def connect(self, slot, type=None):
        if slot not in self._slots:
            self._slots.append(slot)
        return slot

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args):
        if _needs_main_thread():
            _deliver_via_qt(self._slots, args)
            return
        for slot in list(self._slots):
            try:
                slot(*args)
            except Exception:
                continue

    def __repr__(self):
        return f"<Signal{self._types}>"


# ── Entrega al hilo del main loop (solo si Qt está en uso) ─────────
# Los workers (asyncio.to_thread, torrent, etc.) emiten desde hilos
# secundarios; sin Qt la entrega es directa (terminal). Si la app es Qt,
# se postea al main loop como hacía Qt.QueuedConnection, para que los
# slots de la UI actualicen widgets de forma segura.

import queue as _queue

_qt_helper = None
_call_queue = _queue.Queue()


def _needs_main_thread() -> bool:
    try:
        from PySide6.QtCore import QCoreApplication, QThread
        app = QCoreApplication.instance()
        if app is None:
            return False
        # Con stubs/fakes (tests sin Qt real) no hay main loop que entregue.
        if not isinstance(app, QCoreApplication):
            return False
        return QThread.currentThread() is not app.thread()
    except Exception:
        return False


def _deliver_via_qt(slots, args):
    """Entrega los slots en el hilo del main loop.

    IMPORTANTE: NO usar QMetaObject.invokeMethod con Q_ARG(object, ...):
    PySide6 no tiene QMetaType para 'object' y la excepción en el hilo
    worker provoca el cierre del proceso. Los argumentos viajan por una
    cola y el invokeMethod se llama SIN argumentos.
    """
    from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, Qt, Slot

    global _qt_helper
    if _qt_helper is None:
        # El helper se crea SIN parent (puede crearse desde un worker) y se
        # MUEVE al hilo del main loop: así el invokeMethod QueuedConnection
        # entrega siempre en el main thread.
        class _Helper(QObject):
            @Slot()
            def _call(self):
                while True:
                    try:
                        fn, fargs = _call_queue.get_nowait()
                    except _queue.Empty:
                        break
                    try:
                        fn(*fargs)
                    except Exception:
                        continue

        _qt_helper = _Helper()
        _qt_helper.moveToThread(QCoreApplication.instance().thread())
    for slot in list(slots):
        _call_queue.put((slot, args))
        QMetaObject.invokeMethod(_qt_helper, "_call", Qt.QueuedConnection)


def queued_kw():
    """kwargs de conexión: ``type=Qt.QueuedConnection`` si Qt existe, sino {}.

    Permite que un mismo connect() funcione en la UI (entrega en el hilo
    del main loop) y en terminal (entrega directa).
    """
    try:
        from PySide6.QtCore import Qt
        return {"type": Qt.QueuedConnection}
    except Exception:
        return {}
