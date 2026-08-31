"""Cliente del acelerador local Surge.exe (Windows).

Surge es un subproceso que escucha en localhost y acelera descargas HTTP.
Este módulo encapsula: detección del binario, arranque, healthcheck, API
y apagado. El token es aleatorio por sesión (nunca hardcodeado).

Extraído de services/download_engine.py para mantener los archivos por
debajo del límite de ~850 líneas y separar responsabilidades.
"""

import asyncio
import json
import logging
import secrets
import subprocess
import urllib.request
from pathlib import Path

from syops_utils import _NOWINDOW, app_dir

logger = logging.getLogger(__name__)

DEFAULT_PORT = 17890


class SurgeClient:
    """Cliente del subproceso Surge.exe (API localhost)."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        # Token aleatorio por sesión: Surge escucha en localhost pero un
        # token fijo en el código permitiría a cualquier proceso local usar
        # el servicio de descarga.
        self.token = secrets.token_hex(16)
        self.process = None
        self.started = False

    def path(self) -> Path:
        return app_dir() / "surge.exe"

    def check_health(self) -> bool:
        try:
            req = urllib.request.Request(
                f"http://localhost:{self.port}/api/v1/health",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            urllib.request.urlopen(req, timeout=2)
            self.started = True
            return True
        except Exception:
            return False

    async def start(self) -> bool:
        """Arranca el subproceso y espera a que responda. True si quedó listo."""
        if self.started:
            return True
        surge = self.path()
        if not surge.exists():
            return False
        if self.check_health():
            return True
        try:
            self.process = subprocess.Popen(
                [str(surge), "server", "--port", str(self.port),
                 "--token", self.token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NOWINDOW,
            )
            for _attempt in range(10):
                await asyncio.sleep(1)
                if self.check_health():
                    return True
        except Exception as exc:
            logger.warning("Error starting Surge: %s", exc)
        return False

    def api(self, method: str, path: str, data: dict | None = None):
        """Llamada JSON a la API local de Surge."""
        url = f"http://localhost:{self.port}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode())

    def stop(self):
        """Termina el subproceso si está vivo y resetea el estado."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                except Exception:
                    pass
            self.process = None
        self.started = False
