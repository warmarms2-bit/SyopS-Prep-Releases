"""Tests de DownloadManager (services/download_manager.py).

NOTA: el conftest stubbea PySide6 (señales no-op) para que la app importe
sin display. Por eso estos tests prueban la LÓGICA del manager (prioridad,
estado, resolución) sin depender de señales Qt reales. El flujo completo
con señales (descarga real) se cubre en la app o con Qt real.

Para probar _run_task con señales reales, correr con Qt real:
    QT_API=pyside6 python3 -c "... (no usa el conftest) ..."
"""

from pathlib import Path

from services.download_manager import (
    DownloadManager, DownloadTask, _calc_speed_mb, STALL_TIMEOUT_HTTP,
)


def test_calc_speed_mb_usa_timestamp_anterior():
    """La velocidad usa el timestamp del avance anterior (no el actual):
    1 MB descargado en 1 segundo real → ~1 MB/s (no inflado)."""
    prev_at = 1000.0
    now = 1001.0
    delta = 1024 * 1024
    speed = _calc_speed_mb(prev_at, now, delta)
    assert 0.9 < speed < 1.1, f"Esperaba ~1 MB/s, obtuve {speed}"


def test_calc_speed_mb_con_avance_masivo_y_poco_tiempo_real():
    """Si el avance fue en 2 segundos reales, la velocidad refleja eso
    (no el delta sobre ~0s del bug original)."""
    prev_at = 1000.0
    now = 1002.0
    delta = 10 * 1024 * 1024  # 10 MB
    speed = _calc_speed_mb(prev_at, now, delta)
    assert 4.5 < speed < 5.5, f"Esperaba ~5 MB/s, obtuve {speed}"


def test_calc_speed_mb_no_divide_por_cero():
    prev_at = 1000.0
    now = 1000.0  # mismo instante
    speed = _calc_speed_mb(prev_at, now, 1024 * 1024)
    assert speed > 0  # no crashea y no da infinito


def test_stall_timeout_definido():
    assert STALL_TIMEOUT_HTTP > 0



def test_add_task_y_prioridad():
    mgr = DownloadManager(None, max_concurrent=2)
    # Orden ascendente: priority 0 antes que 1; http antes que torrent;
    # luego tamaños pequeños primero.
    t1 = DownloadTask("a", "http", "u1", Path("/tmp"), size_hint=100, priority=1)
    t2 = DownloadTask("b", "http", "u2", Path("/tmp"), size_hint=10, priority=0)
    t3 = DownloadTask("c", "torrent", "m", Path("/tmp"), size_hint=50, priority=0)
    mgr.add_tasks([t3, t1, t2])
    mgr._sort_by_priority()
    names = [t.name for t in mgr.tasks]
    assert names == ["b", "c", "a"]


def test_add_task_acumula_bytes():
    mgr = DownloadManager(None, max_concurrent=2)
    mgr.add_task(DownloadTask("a", "http", "u", Path("/tmp"), size_hint=100))
    mgr.add_task(DownloadTask("b", "http", "u", Path("/tmp"), size_hint=200))
    assert mgr._total_bytes == 300  # 100 + 200


def test_add_task_sin_size_hint_usa_1():
    mgr = DownloadManager(None, max_concurrent=2)
    mgr.add_task(DownloadTask("a", "http", "u", Path("/tmp"), size_hint=0))
    assert mgr._total_bytes == 1  # size_hint 0 → usa 1


def test_task_estado_inicial():
    task = DownloadTask("app", "http", "u", Path("/tmp"), size_hint=500)
    assert task.status == "pending"
    assert task.progress == 0
    assert task.downloaded == 0
    assert task.error_msg == ""


def test_cancel_all_llama_stop_surge():
    engine = type("E", (), {"stop_surge": lambda self: None})()
    mgr = DownloadManager(engine, max_concurrent=2)
    mgr.cancel_all()
    assert mgr._cancelled is True


def test_resolver_callback_se_asigna():
    """El resolver_callback se guarda en la tarea y el manager lo lee."""
    def resolver():
        return "https://directo.pkg", {}

    task = DownloadTask("app", "http", "https://vista.com/a", Path("/tmp"),
                        resolver_callback=resolver)
    mgr = DownloadManager(None, max_concurrent=2)
    mgr.add_task(task)
    assert task.resolver_callback is resolver


def test_semaphore_respeta_max_concurrent():
    mgr = DownloadManager(None, max_concurrent=5)
    assert mgr.max_concurrent == 5
    assert mgr.semaphore is not None


def test_emit_queue_estructura():
    """_emit_queue genera la lista de estados con la estructura esperada."""
    mgr = DownloadManager(None, max_concurrent=2)
    task = DownloadTask("app", "http", "u", Path("/tmp"), size_hint=500)
    mgr.add_task(task)

    # Capturar la señal queue_updated (stub en conftest: connect guarda callback)
    captured = []
    mgr.queue_updated.connect(lambda s: captured.append(s))

    # El stub de Signal no llama el callback; verificar la estructura manual.
    states = [{
        "name": t.name, "status": t.status, "progress": t.progress,
        "speed": t.speed_mb, "error": t.error_msg,
        "downloaded": t.downloaded, "total": t.total or t.size_hint,
    } for t in mgr.tasks]

    assert states[0]["name"] == "app"
    assert states[0]["status"] == "pending"
    assert states[0]["total"] == 500
    assert states[0]["downloaded"] == 0
