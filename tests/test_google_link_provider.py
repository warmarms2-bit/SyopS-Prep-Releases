"""Tests del proveedor de links vía Google Apps Script (Tier 1.5).

Verifica que el cliente pide `action=get_link`, valida activación contra el
script y recibe la URL del file-host SOLO si el código es válido. Usa un
servidor HTTP local que imita el `doGet` del Apps Script.
"""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services.google_link_provider import GoogleLinkProvider, GoogleLinkError


class _FakeAppsScript(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        q = urllib.parse.urlparse(self.path)
        p = urllib.parse.parse_qs(q.query)
        def one(k):
            v = p.get(k, [""])
            return v[0] if v else ""
        action = one("action")
        if action != "get_link":
            self._json({"status": "error", "message": "accion desconocida"})
            return
        if one("code") != "CODIGO-OK":
            self._json({"status": "error", "message": "Codigo no encontrado"})
            return
        if not one("name"):
            self._json({"status": "error", "message": "Faltan code o name"})
            return
        self._json({"status": "ok",
                    "url": f"https://file-host.ejemplo/{one('name')}.bin",
                    "name": one("name")})

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def script_url():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAppsScript)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_pide_get_link_y_entrega_url(script_url):
    prov = GoogleLinkProvider(script_url, "C1", "H1", "CODIGO-OK")
    data = prov.request("Blender", "http", "mac")
    assert data["name"] == "Blender"
    assert data["url"] == "https://file-host.ejemplo/Blender.bin"


def test_codigo_invalido_rechaza(script_url):
    prov = GoogleLinkProvider(script_url, "C1", "H1", "CODIGO-MALO")
    with pytest.raises(GoogleLinkError) as exc:
        prov.request("Blender", "http", "mac")
    assert "no encontrado" in str(exc.value)


def test_sin_script_lanza_error():
    prov = GoogleLinkProvider("", "C1", "H1", "CODIGO-OK")
    with pytest.raises(GoogleLinkError):
        prov.request("Blender", "http", "mac")
