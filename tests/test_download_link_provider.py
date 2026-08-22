"""Tests de seguridad Tier 2: links server-side.

Verifica que el cliente (DownloadLinkProvider) obtiene un link firmado del
servidor y descarga el archivo SIN conocer la URL del file-host, que el
servidor exige activación, y que los tokens son de un solo uso.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from services.download_link_provider import DownloadLinkProvider, DownloadLinkError
from server.syops_server import make_server

FILE_HOST = "https://file-host.ejemplo/archivo-secreto.bin"


@pytest.fixture()
def server(tmp_path):
    """Servidor de prueba con catálogo y activación inyectados."""
    payload = b"CONTENIDO-DEL-ARCHIVO"
    src = tmp_path / "payload.bin"
    src.write_bytes(payload)

    def _resolve(kind, name, method, platform):
        # El "file-host" es un archivo local; el cliente jamás debe ver esta URL.
        return f"file://{src}", name

    def _authorize(client_id, hwid, code):
        return code == "CODIGO-OK"

    httpd = make_server(0, resolve_fn=_resolve, authorize_fn=_authorize)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _request(url, data=None):
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_sin_activacion_rechaza(server):
    prov = DownloadLinkProvider(server, "C1", "H1", "CODIGO-MALO")
    with pytest.raises(DownloadLinkError) as exc:
        prov.request("Blender", "http", "mac")
    assert "activación" in str(exc.value).lower() or "401" in str(exc.value)


def test_con_activacion_entrega_link_del_servidor(server):
    prov = DownloadLinkProvider(server, "C1", "H1", "CODIGO-OK")
    data = prov.request("Blender", "http", "mac")
    assert data["name"] == "Blender"
    assert "/v1/download/" in data["url"]
    assert data["url"].startswith(server)  # apunta al SERVIDOR
    assert FILE_HOST not in data["url"]    # el cliente NO ve la URL del file-host


def test_token_un_solo_uso_y_streaming(server):
    prov = DownloadLinkProvider(server, "C1", "H1", "CODIGO-OK")
    data = prov.request("Blender", "http", "mac")
    dl_url = data["url"]

    status, body = _request(dl_url)
    assert status == 200
    assert body == b"CONTENIDO-DEL-ARCHIVO"  # streaming del servidor

    # Segundo uso del mismo token → rechazado (un solo uso).
    status2, _ = _request(dl_url)
    assert status2 == 410


def test_request_body_invalido(server):
    status, _ = _request(server + "/v1/download/request", data={"raro": 1})
    assert status in (400, 401, 404)


def test_download_token_invalido(server):
    status, _ = _request(server + "/v1/download/token-falso")
    assert status == 410
