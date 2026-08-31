"""Proveedor de links de descarga vía servidor (Tier 2).

El cliente NO conoce las URLs del file-host. Pide al servidor un link de
descarga firmado y de corta duración; el servidor valida la activación y
hace streaming del archivo. El `DownloadTask` del cliente apunta al servidor,
nunca al file-host, así que no hay URL de origen que extraer.

Uso:

    prov = DownloadLinkProvider(SERVER_URL, client_id, hwid, code)
    data = prov.request("Blender", "http", "mac", max_apps=3)
    # data = {"url": ".../v1/download/<token>", "name": "Blender", "expires_in": 300}
    # luego: DownloadTask(name, "http", data["url"], output_dir, size_hint)
"""

import json
import urllib.error
import urllib.request


class DownloadLinkError(Exception):
    """Error al obtener un link del servidor (auth, red o respuesta inválida)."""


class DownloadLinkProvider:
    """Cliente del servidor de links (sin conocimiento del catálogo)."""

    def __init__(self, base_url: str, client_id: str, hwid: str, code: str,
                 timeout: int = 20):
        self.base_url = (base_url or "").rstrip("/")
        self.client_id = client_id
        self.hwid = hwid
        self.code = code
        self.timeout = timeout

    def request(self, name: str, method: str, platform: str,
                max_apps: int = 3, kind: str = "app") -> dict:
        """Solicita un link firmado para una descarga.

        `kind` puede ser "app" (una app Adobe o normal), "tool" (una
        herramienta auxiliar) o "fullpack" (el collection AIO). Devuelve
        `{"url": <url completa del servidor>, "name": <nombre>, "expires_in"}`.
        Lanza `DownloadLinkError` si el servidor rechaza (sin activación /
        código) o no responde.
        """
        if not self.base_url:
            raise DownloadLinkError("servidor de links no configurado")
        payload = json.dumps({
            "client_id": self.client_id,
            "hwid": self.hwid,
            "code": self.code,
            "kind": kind,
            "name": name,
            "method": method,
            "platform": platform,
            "max_apps": int(max_apps or 0),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/download/request",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                body = {}
            raise DownloadLinkError(
                body.get("error") or f"HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DownloadLinkError(f"sin conexión al servidor: {exc}") from exc

        if not isinstance(data, dict) or not data.get("url"):
            raise DownloadLinkError(data.get("error") or "respuesta inválida")
        data["url"] = f"{self.base_url}{data['url']}"
        return data


def fetch_tools_map(sheets_url: str, timeout: int = 15) -> list:
    """Obtiene el mapping tool→apps_destino desde la hoja Links (GET).

    Devuelve lista de dicts ``[{name, apps_destino}, ...]`` de las filas
    ``kind=tool``.  Se usa en el planner para saber qué tools acompañan a
    cada app sin hardcodear.
    """
    sep = "&" if "?" in sheets_url else "?"
    url = f"{sheets_url}{sep}action=get_tools_map"
    req = urllib.request.Request(url, headers={"User-Agent": "SyopsWizard/1.3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("status") != "ok":
        return []
    return data.get("tools", [])
