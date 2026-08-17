#!/usr/bin/env python3
import json
import logging
import threading
import urllib.request
from datetime import datetime


logger = logging.getLogger(__name__)


class SheetsReporter:
    def __init__(self, url, session_id, client_id, version):
        self.url = url
        self.session_id = session_id
        self.client_id = client_id
        self.version = version

    def _post_via_get(self, data):
        """Fallback GET para despliegues que no aceptan POST."""
        try:
            import urllib.parse
            payload = json.dumps(data)
            encoded = urllib.parse.quote(payload, safe="")
            sep = "&" if "?" in self.url else "?"
            url = f"{self.url}{sep}payload={encoded}"
            req = urllib.request.Request(
                url,
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read().decode("utf-8")
            try:
                result = json.loads(raw)
            except Exception:
                result = None
            if isinstance(result, dict) and result.get("status") == "error":
                logger.warning("Backend error (GET fallback): %s", result.get("message", ""))
                return False
            logger.debug("GET fallback OK")
            return True
        except Exception as e2:
            logger.warning("Error GET fallback: %s", e2)
            return False

    def _post(self, data, allow_get_fallback=True):
        if not self.url:
            return False
        try:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read().decode("utf-8")
            try:
                result = json.loads(raw)
            except Exception:
                result = None
            if isinstance(result, dict) and result.get("status") == "error":
                logger.warning("Backend error: %s", result.get("message", ""))
                return False
            return True
        except Exception as e:
            logger.warning("Error posting: %s", e)
            if allow_get_fallback:
                return self._post_via_get(data)
            return False

    def _post_sync(self, data, allow_get_fallback=True):
        """Synchronous version - blocks until complete."""
        return self._post(data, allow_get_fallback=allow_get_fallback)

    def _post_async(self, data, allow_get_fallback=True):
        threading.Thread(target=self._post, args=(data, allow_get_fallback), daemon=True).start()

    def _scan_payload(self, scan_data, hwid=""):
        data = {
            "so": scan_data.get("os", ""),
            "cpu": scan_data.get("cpu", ""),
            "ram": scan_data.get("ram", ""),
        }
        disk = scan_data.get("disk", {})
        if disk:
            data["disco_total"] = disk.get("total", "")
            data["disco_libre"] = disk.get("free", "")
        if hwid:
            data["hwid"] = hwid
        return data

    def send_session(self, scan_data, hwid: str = ""):
        """Registra una sesión en la hoja 'Sesiones' SOLO cuando el usuario
        llega a la pantalla de ingreso del código de activación."""
        if not scan_data:
            return False
        data = self._scan_payload(scan_data, hwid)
        data.update({
            "action": "session",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "version": self.version,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        logger.debug("send_session: session_id=%s client_id=%s", self.session_id, self.client_id)
        self._post_async(data)
        return True

    def send_selection(self, apps, method):
        apps_str = ", ".join(apps) if apps else ""
        logger.debug("send_selection: session_id=%s apps=%s method=%s", self.session_id, apps_str, method)
        self._post_async({
            "action": "update",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "estado": "seleccionado",
            "apps": apps_str,
            "method": method or "",
        })

    def send_downloading(self, apps):
        logger.debug("send_downloading: session_id=%s apps=%s", self.session_id, apps)
        self._post_async({
            "action": "update",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "estado": "descargando",
            "apps": ", ".join(apps) if apps else "",
        })

    def send_completed(self, password=None, apps=None, method: str = "", ruta=None,
                       ruta_proforma=None, horarios=None, hwid: str = "", sync=False):
        apps_str = ", ".join(apps) if apps else ""
        logger.debug("send_completed: session_id=%s apps=%s method=%s", self.session_id, apps_str, method)
        data = {
            "action": "update",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "estado": "completado",
            "apps": apps_str,
            "method": method or "",
        }
        if hwid:
            data["hwid"] = hwid
        self._post_async(data)

    def send_closed(self, nombre=None, phone=None, scan_data=None,
                    apps=None, ruta=None, password=None,
                    ruta_proforma=None, horarios=None, hwid: str = "", sync=False):
        apps_str = ", ".join(apps) if apps else ""
        logger.debug("send_closed: session_id=%s apps=%s", self.session_id, apps_str)
        data = {
            "action": "new_service",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "ultima_sesion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "apps": apps_str,
        }
        if hwid:
            data["hwid"] = hwid
        if scan_data:
            data.update(self._scan_payload(scan_data, hwid))
        self._post_async(data)

    def get_clients(self):
        if not self.url:
            return []
        try:
            url = self.url + "?action=get_clients"
            req = urllib.request.Request(
                url,
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if data.get("status") == "ok":
                return data.get("clients", [])
            return []
        except Exception as e:
            logger.warning("Error getting clients: %s", e)
            return []

    def send_activation(self, client_id, max_apps: int = 3, code: str = "", hwid: str = ""):
        logger.debug("send_activation: session_id=%s code=%s max_apps=%s", self.session_id, code, max_apps)
        self._post_async({
            "action": "update",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "estado": "activado",
            "max_apps": max_apps,
            "code": code,
            "hwid": hwid,
        })

    def send_error(self, error_text):
        logger.debug("send_error: session_id=%s error=%s", self.session_id, str(error_text)[:2000])
        self._post_async({
            "action": "error",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "error": str(error_text)[:2000],
        })

    def send_cancelled(self, sync=False):
        data = {
            "action": "update",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "estado": "cancelado",
        }
        if sync:
            return self._post_sync(data)
        self._post_async(data)

    def _get(self, params):
        if not self.url:
            return None
        try:
            import urllib.parse
            query = urllib.parse.urlencode(params)
            url = self.url
            if "?" in url:
                url = url + "&" + query
            else:
                url = url + "?" + query
            req = urllib.request.Request(
                url,
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            logger.warning("Error GET: %s", e)
            return None

    def check_code(self, code: str, hwid: str = ""):
        """Consulta el backend para saber si un código está disponible.
        Retorna el dict completo del backend, que ahora incluye 'type'.
        """
        return self._get({
            "action": "check_code",
            "code": code,
            "hwid": hwid,
            "client_id": self.client_id,
        })

    def check_code_async(self, code: str, hwid: str = "", callback=None):
        """Versión asíncrona de check_code. Ejecuta en un thread y llama
        al callback(result) en el main thread vía signal, sin bloquear el
        hilo de Qt/asyncio. Usa un bridge descartable por llamada (no
        comparte signal con otras llamadas concurrentes), de modo que un
        reintento no acumula callbacks y no se puede activar dos veces."""
        from PySide6.QtCore import QObject, Signal, Qt
        class _OneShotBridge(QObject):
            result_ready = Signal(object)
        bridge = _OneShotBridge()
        if not hasattr(self, "_pending_bridges"):
            self._pending_bridges = []
        self._pending_bridges.append(bridge)
        def _cleanup_and_call(result):
            try:
                if callback:
                    callback(result)
            finally:
                if bridge in self._pending_bridges:
                    self._pending_bridges.remove(bridge)
        bridge.result_ready.connect(_cleanup_and_call, Qt.QueuedConnection)
        def _run():
            try:
                result = self.check_code(code, hwid)
            except Exception as e:
                logger.warning("check_code_async error: %s", e)
                result = None
            bridge.result_ready.emit(result)
        threading.Thread(target=_run, daemon=True).start()

    def get_code_type(self, code: str, hwid: str = "") -> str:
        """Retorna 'standard' o 'adobe_full_pack' según el backend."""
        info = self.check_code(code, hwid)
        if not info:
            return "standard"
        return info.get("type", "standard") if isinstance(info, dict) else "standard"

    def use_code(self, code: str, hwid: str = "", max_apps: int = 3, sync=False):
        """Marca un código como usado en el backend."""
        data = {
            "action": "use_code",
            "session_id": self.session_id,
            "client_id": self.client_id,
            "code": code,
            "hwid": hwid,
            "max_apps": max_apps,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if sync:
            return self._post_sync(data)
        self._post_async(data)

    def use_code_async(self, code: str, hwid: str = "", max_apps: int = 3, callback=None):
        """Versión asíncrona de use_code. Ejecuta en un thread y llama
        al callback(result: bool) en el main thread vía signal, sin
        bloquear el hilo de Qt/asyncio. Usa un bridge descartable por
        llamada (no comparte signal con otras llamadas concurrentes)."""
        from PySide6.QtCore import QObject, Signal, Qt
        class _OneShotBridge(QObject):
            result_ready = Signal(object)
        bridge = _OneShotBridge()
        if not hasattr(self, "_pending_bridges"):
            self._pending_bridges = []
        self._pending_bridges.append(bridge)
        def _cleanup_and_call(result):
            try:
                if callback:
                    callback(result)
            finally:
                if bridge in self._pending_bridges:
                    self._pending_bridges.remove(bridge)
        bridge.result_ready.connect(_cleanup_and_call, Qt.QueuedConnection)
        def _run():
            try:
                result = self.use_code(code, hwid, max_apps, sync=True)
            except Exception as e:
                logger.warning("use_code_async error: %s", e)
                result = False
            bridge.result_ready.emit(result)
        threading.Thread(target=_run, daemon=True).start()
