"""Proveedor de links vía Google Apps Script (Tier 1.5).

El catálogo de URLs vive en una Google Sheet ("Links"); el wizard pide el
link de cada app con `action=get_link`. El Apps Script valida el código de
activación contra la hoja "Clientes" y devuelve la URL. El cliente no trae
el catálogo embebido; solo recibe el link de la app que pidió (y solo si
está activado).

Misma interfaz que `DownloadLinkProvider` para que el planner sea agnóstico
del backend.
"""

import json
import urllib.error
import urllib.parse
import urllib.request


class GoogleLinkError(Exception):
    """Error al obtener un link del Apps Script (auth, red o sin link)."""


class GoogleLinkProvider:
    """Cliente del endpoint `get_link` de Google Apps Script."""

    def __init__(self, script_url: str, client_id: str, hwid: str, code: str,
                 timeout: int = 90):
        self.script_url = (script_url or "").strip()
        self.client_id = client_id
        self.hwid = hwid
        self.code = code
        self.timeout = timeout

    def request(self, name: str, method: str, platform: str,
                max_apps: int = 3, kind: str = "app") -> dict:
        """Pide el link de una descarga.

        Devuelve `{"url": <url del file-host>, "name": <nombre>}` o lanza
        `GoogleLinkError`. El `kind` se ignora (la hoja "Links" distingue por
        `metodo`); se mantiene por compatibilidad con el planner.
        """
        if not self.script_url:
            raise GoogleLinkError("Google Apps Script no configurado")
        params = urllib.parse.urlencode({
            "action": "get_link",
            "client_id": self.client_id,
            "hwid": self.hwid,
            "code": self.code,
            "name": name,
            "method": method or "",
            "platform": platform or "",
        })
        url = f"{self.script_url}?{params}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise GoogleLinkError(f"sin conexión al script: {exc}") from exc

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raise GoogleLinkError("respuesta no JSON del script") from None

        if not isinstance(data, dict) or data.get("status") != "ok" or not data.get("url"):
            raise GoogleLinkError(
                str(data.get("message") or data.get("error") or "respuesta inválida")
            )
        result = {"url": data["url"], "name": data.get("name") or name}
        if data.get("resolver"):
            result["resolver"] = data["resolver"]
        return result
