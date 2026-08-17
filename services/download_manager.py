import asyncio
import math
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse
from services.signals import Signal, queued_kw
from services.http_utils import _safe_eta, _format_eta
from services.download_config import STALL_TIMEOUT_HTTP, STALL_TIMEOUT_TORRENT
from i18n import _

# Re-export para compatibilidad con imports históricos.
__all__ = ["DownloadManager", "DownloadTask", "STALL_TIMEOUT_HTTP", "STALL_TIMEOUT_TORRENT"]

# Callback que resuelve URL directa + headers extra antes de descargar.
# Devuelve (resolved_url: str, headers_extra: dict[str, str]).
ResolverCallback = Callable[[], tuple[str, dict[str, str]]] | None


def _calc_speed_mb(prev_at: float, now: float, delta_bytes: int) -> float:
    """Velocidad en MB/s entre dos eventos de progreso.

    Usa el timestamp del avance ANTERIOR (no el actual) para que elapsed
    sea real; si se usara el actual, elapsed ≈ 0 y la velocidad se inflaría.
    """
    elapsed = max(now - prev_at, 0.001)
    return (delta_bytes / elapsed) / (1024 * 1024)


class DownloadTask:
    def __init__(self, name: str, method: str, url_or_magnet: str, dest_dir: Path,
                 size_hint: int = 0, priority: int = 0,
                 resolver_callback: ResolverCallback = None):
        self.name = name
        self.method = method
        self.url_or_magnet = url_or_magnet
        self.dest_dir = dest_dir
        self.size_hint = size_hint
        self.priority = priority
        self.resolver_callback = resolver_callback
        self.status = "pending"
        self.progress = 0
        self.speed_mb = 0.0
        self.downloaded = 0
        self.total = 0
        self.error_msg = ""
        self._last_downloaded = 0
        self._last_progress_at = 0
        self._stall_deadline = 0


class DownloadManager:
    task_progress = Signal(str, int, str)
    # El tercer parametro es el tamaño en bytes; se usa int (64 bits en
    # Python) — con Qt no hay qint64, no hay limite.
    task_completed = Signal(str, bool, int)
    queue_updated = Signal(list)
    eta_global_changed = Signal(str)
    task_stalled = Signal(str, str)  # name, reason

    def __init__(self, engine, max_concurrent: int = 3):
        self.engine = engine
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.tasks = []
        self._total_bytes = 0
        self._completed_bytes = 0
        self._cancelled = False
        self._started_at = 0

    def add_task(self, task: DownloadTask):
        self.tasks.append(task)
        self._total_bytes += task.size_hint or 1

    def add_tasks(self, tasks: list):
        for t in tasks:
            self.add_task(t)

    def _sort_by_priority(self):
        # Prioridad: 1) prioridad manual, 2) metodo (http antes que torrent),
        # 3) tamaño (pequeños primero).
        def _key(t: DownloadTask):
            method_priority = {"http": 0, "torbox": 1, "torrent": 2}
            size = t.size_hint or (10 * 1024 ** 3)
            return (t.priority, method_priority.get(t.method, 9), size)
        self.tasks.sort(key=_key)

    async def start_all(self):
        self._sort_by_priority()
        self._started_at = time.time()
        pending = [t for t in self.tasks if t.status == "pending"]
        if not pending:
            return
        self._emit_queue()
        # El monitor de stall se implementa dentro de _await_with_stall
        # (por tarea, sin tarea asyncio paralela) para evitar el RuntimeError
        # de qasync con tareas intercaladas.
        tasks = [asyncio.create_task(self._run_task(t)) for t in pending]
        for coro in asyncio.as_completed(tasks):
            if self._cancelled:
                break
            try:
                await coro
            except Exception:
                pass
        self._emit_queue()

    async def _resolve_task(self, task: DownloadTask) -> tuple[str, dict[str, str]]:
        """Resuelve URL y headers extra si la tarea tiene resolver_callback."""
        if task.resolver_callback is None:
            return task.url_or_magnet, {}
        # Ejecutar callback bloqueante en thread pool para no congelar el loop.
        return await asyncio.to_thread(task.resolver_callback)

    async def _run_task(self, task: DownloadTask):
        async with self.semaphore:
            if self._cancelled:
                return

            # 1) Resolución previa (URL directa + headers custom).
            try:
                resolved_url, headers_extra = await self._resolve_task(task)
            except Exception as e:
                task.status = "failed"
                task.error_msg = str(e)[:120]
                self.task_completed.emit(task.name, False, 0)
                self._emit_queue()
                return

            task.status = "downloading"
            task._last_progress_at = time.time()
            task._stall_deadline = time.time() + (
                STALL_TIMEOUT_TORRENT if task.method == "torrent" else STALL_TIMEOUT_HTTP
            )
            self._emit_queue()
            future = asyncio.get_running_loop().create_future()

            def on_progress(name, pct, status, downloaded, total):
                try:
                    if name != task.name:
                        return
                    task.progress = pct
                    task.status = "downloading"
                    now = time.time()
                    # Velocidad aproximada para UI (usando el timestamp del
                    # avance anterior, antes de sobreescribir _last_progress_at).
                    if total > 0 and downloaded > task.downloaded:
                        prev = task._last_progress_at or now
                        delta = downloaded - task.downloaded
                        task.speed_mb = _calc_speed_mb(prev, now, delta)
                    # Actualizar marcas de avance (bytes, timestamp, deadline)
                    if downloaded > task._last_downloaded or total != task.total:
                        task._last_downloaded = downloaded
                        task._last_progress_at = now
                        task._stall_deadline = now + (
                            STALL_TIMEOUT_TORRENT if task.method == "torrent" else STALL_TIMEOUT_HTTP
                        )
                    if total > 0:
                        task.total = total
                        task.downloaded = downloaded
                    self.task_progress.emit(name, pct, status)
                    # Refrescar la cola global en cada evento para que la barra
                    # de progreso total y el contador X/Y avancen en tiempo real.
                    try:
                        self._emit_queue()
                    except Exception:
                        pass
                except Exception:
                    # No dejar que una excepcion en el slot rompa el loop de eventos
                    pass

            def on_complete(name, success, size):
                try:
                    if name != task.name or future.done():
                        return
                    if success:
                        try:
                            if isinstance(size, (int, float)) and math.isfinite(size):
                                sz = int(size)
                            else:
                                sz = int(task.total or task.size_hint or 1)
                        except Exception:
                            sz = int(task.total or task.size_hint or 1)
                        self._completed_bytes += sz
                    future.set_result(success)
                except Exception:
                    pass

            try:
                self.engine.progress.connect(on_progress, **queued_kw())
                self.engine.completed.connect(on_complete, **queued_kw())
            except Exception:
                pass

            try:
                self.task_progress.emit(task.name, 0, _("descarga.status_descargando"))
                self._emit_queue()

                if resolved_url.startswith("file://"):
                    local_path = Path(unquote(urlparse(resolved_url).path))
                    if not local_path.is_file():
                        raise RuntimeError(_("descarga.error_navegador"))
                    size = local_path.stat().st_size
                    task.total = size
                    task.downloaded = size
                    self.task_progress.emit(task.name, 100, _("descarga.descarga_completada"))
                    on_complete(task.name, True, size)
                    success = True
                elif task.method == "torbox":
                    coro = self._download_via_torbox(task, on_progress)
                    success = await self._await_with_stall(task, coro, future)
                elif task.method == "http":
                    coro = self.engine.download_http(task.name, resolved_url, task.dest_dir, headers_extra)
                    success = await self._await_with_stall(task, coro, future)
                elif task.method == "torrent":
                    coro = self.engine.download_torrent(task.name, task.url_or_magnet, task.dest_dir)
                    success = await self._await_with_stall(task, coro, future)
                else:
                    coro = self.engine.download_http(task.name, resolved_url, task.dest_dir, headers_extra)
                    success = await self._await_with_stall(task, coro, future)

                if success:
                    task.status = "completed"
                    task.progress = 100
                    if task.total and task.downloaded == 0:
                        task.downloaded = task.total
                else:
                    task.status = "failed"
                    task.error_msg = _("descarga.error_durante_descarga")
            except BaseException as e:
                try:
                    import traceback as _tb
                    lp = Path(__file__).parent / "syops_error.log"
                    with open(lp, "a", encoding="utf-8") as _f:
                        _f.write("=" * 60 + "\n[_run_task] BASEEXCEPTION\n")
                        _f.write(_tb.format_exc() + "\n")
                except Exception:
                    pass
                task.status = "failed"
                task.error_msg = str(e)[:120]
            finally:
                try:
                    self.engine.progress.disconnect(on_progress)
                    self.engine.completed.disconnect(on_complete)
                except Exception:
                    pass
                if task.status == "failed":
                    self.task_completed.emit(task.name, False, 0)
                else:
                    self.task_completed.emit(task.name, True, task.total or task.size_hint or 1)
                self._emit_queue()

    async def _await_with_stall(self, task: DownloadTask, coro, future) -> bool:
        """Espera el resultado del engine verificando el deadline de stall.

        Correr la descarga como tarea en vez de bloquear el event loop
        permite verificar en cada iteración si no hubo avance de bytes
        durante STALL_TIMEOUT_*: si es así, marca la tarea como estancada,
        emite task_stalled y cancela la descarga. No crea un monitor
        asyncio paralelo (que generaba RuntimeError en qasync).
        """
        try:
            dl = asyncio.create_task(coro)
        except Exception:
            await coro
            dl = None

        while not future.done():
            # Stall: sin avance de bytes dentro del timeout.
            if time.time() > task._stall_deadline:
                task.status = "failed"
                task.error_msg = _("descarga.error_estancada")
                self.task_stalled.emit(task.name, "stall_timeout")
                if dl is not None:
                    dl.cancel()
                    try:
                        await dl
                    except (asyncio.CancelledError, Exception):
                        pass
                return False
            if dl is not None and dl.done():
                # El engine terminó: si con error (sin emitir completed),
                # fallar de inmediato en vez de esperar el stall deadline.
                try:
                    exc = dl.exception()
                except asyncio.CancelledError:
                    exc = None
                if exc is not None:
                    task.status = "failed"
                    task.error_msg = str(exc)[:120]
                    return False
            await asyncio.sleep(1)

        return bool(future.result() if future.done() else False)

    async def _download_via_torbox(self, task: DownloadTask, on_progress):
        from services import resolver_gateway

        torbox_provider = resolver_gateway.torbox
        if torbox_provider is None:
            raise Exception(_("descarga.error_torbox_sin_link"))

        def poll_cb(name, pct):
            task.progress = int(pct)
            self.task_progress.emit(task.name, int(pct),
                                    _("descarga.torbox_procesando", pct=int(pct)))

        self.task_progress.emit(task.name, 0, _("descarga.torbox_conectando"))
        result = await asyncio.to_thread(
            torbox_provider.resolve_to_direct_url,
            task.url_or_magnet,
            None,
            poll_cb,
        )
        direct_url = result.get("download_url", "")
        if not direct_url:
            raise Exception(_("descarga.error_torbox_sin_link"))

        self.task_progress.emit(task.name, 100, _("descarga.torbox_descargando"))
        await self.engine.download_http(task.name, direct_url, task.dest_dir)

    def cancel_all(self):
        self._cancelled = True
        if self.engine:
            self.engine.stop_surge()

    def _emit_queue(self):
        statuses = []
        for t in self.tasks:
            statuses.append({
                "name": t.name,
                "status": t.status,
                "progress": t.progress,
                "speed": t.speed_mb,
                "error": t.error_msg,
                "downloaded": t.downloaded,
                "total": t.total or t.size_hint,
            })
        self.queue_updated.emit(statuses)

        # ETA global basada en bytes reales cuando se conocen
        elapsed = max(time.time() - self._started_at, 1)
        total_known = sum((t.total or t.size_hint or 0) for t in self.tasks)
        completed = sum((t.downloaded or 0) for t in self.tasks)
        # Velocidad ponderada: promedio de bytes completados / tiempo
        speed = completed / elapsed if completed > 0 else 0
        remaining = max(total_known - completed, 0)
        if speed > 0 and remaining > 0:
            eta_str = _format_eta(_safe_eta(remaining / speed))
        else:
            # Fallback a size_hint si no hay progreso real todavia
            total_hint = sum((t.size_hint or 1) for t in self.tasks)
            remaining_hint = max(total_hint - self._completed_bytes, 0)
            speed_hint = self._completed_bytes / elapsed if self._completed_bytes > 0 else 0
            if speed_hint > 0 and remaining_hint > 0:
                eta_str = _format_eta(_safe_eta(remaining_hint / speed_hint))
            else:
                eta_str = _("descarga.status_calculando")
        self.eta_global_changed.emit(eta_str)
