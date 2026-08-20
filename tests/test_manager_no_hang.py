"""Regresión: el manager no debe colgarse si el engine retorna sin emitir
`completed` (ni retorno mudo, ni CancelledError). v1.3.9.
"""
import asyncio
from pathlib import Path

import pytest

from services.download_manager import DownloadManager, DownloadTask


class _EngineMudo:
    """Engine que 'descarga' y retorna sin emitir ninguna señal de completion."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.progress = None
        self.completed = None

    async def download_http(self, name, url, dest_dir, headers_extra=None):
        await asyncio.sleep(self.delay)
        return


class _EngineCancelado:
    """Engine cuya coroutine lanza CancelledError a mitad de ruta."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.progress = None
        self.completed = None

    async def download_http(self, name, url, dest_dir, headers_extra=None):
        await asyncio.sleep(self.delay)
        raise asyncio.CancelledError


@pytest.mark.parametrize("engine_cls", [_EngineMudo, _EngineCancelado])
def test_start_all_no_cuelga_si_engine_retorna_sin_completed(engine_cls):
    engine = engine_cls()
    manager = DownloadManager(engine, 1)
    task = DownloadTask("prueba", "http", "https://example.com/x.tmp",
                        Path("/tmp/syops_test_out"), 1000)
    manager.add_task(task)

    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(
                asyncio.wait_for(manager.start_all(), timeout=5)
            )
        except asyncio.TimeoutError as exc:
            raise AssertionError(
                f"COLGA: {engine_cls.__name__} no terminó en 5s"
            ) from exc
    finally:
        loop.close()

    assert task.status == "failed"
    assert task.error_msg
