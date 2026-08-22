"""Paridad y orden de validación de la firma HMAC del backend (Apps Script).

El Apps Script valida la firma HMAC de los códigos (capa 1) ANTES de tocar
estado/expiración/hwid (capa 2) en check_code, use_code y get_link. Estos
tests:

  1. Reimplementan `codeSignatureValid` (google_apps_script.js) en Python
     para verificar la paridad con el generador del cliente.
  2. Simulan las 3 acciones (check_code / use_code / get_link) y chequean el
     ORDEN de las comprobaciones (firma primero).
  3. Ejecutan la función REAL del google_apps_script.js en Node (si hay node)
     para confirmar que la firma generada por Python es aceptada por el
     código desplegado.
"""

import datetime
import hashlib
import hmac
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from services import activation

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "google_apps_script.js"
HELPER = REPO_ROOT / "tests" / "_js_signature_check.cjs"
TEST_SECRET = "test-secret-para-tests-1234567890abcdef"

CODE_LENGTH = activation.CODE_LENGTH


# ── Port de la implementación JS a Python (paridad exacta) ─────────────

_JS_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _js_base32_encode(data) -> str:
    """Réplica de base32Encode(bytes) del Apps Script (bit a bit)."""
    bits = "".join(f"{b & 0xFF:08b}" for b in data)
    out = []
    for i in range(0, len(bits), 5):
        chunk = bits[i:i + 5]
        if not chunk:
            break
        padded = chunk + "0" * (5 - len(chunk))
        out.append(_JS_ALPHABET[int(padded, 2)])
    return "".join(out)


def _js_iso_week(dt: datetime.datetime):
    """Réplica de getIsoWeek(date) del Apps Script (ISO 8601)."""
    day = dt.weekday()  # 0=lunes, 6=domingo (igual que el JS día normalizado)
    thursday = dt - datetime.timedelta(days=day - 3)
    year = thursday.year
    jan1 = datetime.datetime(year, 1, 1)
    jan1_day = jan1.weekday()
    first_thursday = jan1 + datetime.timedelta(days=((3 - jan1_day) + 7) % 7)
    diff = (thursday - first_thursday).days
    return year, diff // 7 + 1


def _js_signature_valid(code: str, cid: str, hid: str, secret: str) -> bool:
    """Réplica de codeSignatureValid() del Apps Script (lookback 4 semanas)."""
    code = (code or "").strip().upper()
    cid = (cid or "").strip().upper()
    hid = (hid or "").strip().upper()
    if len(code) != CODE_LENGTH or not cid or not hid:
        return False
    nonce = code[:4]
    code_hash = code[4:]
    now = datetime.datetime.now()
    for i in range(5):  # semana actual + 4 previas
        dt = now - datetime.timedelta(days=i * 7)
        year, week = _js_iso_week(dt)
        period = f"{year}-W{week}"
        for max_apps in (1, 3, 99):
            for valid_days in (7, 30, 365):
                payload = f"{nonce}:{cid}:{hid}:{max_apps}:{period}:{valid_days}"
                digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
                expected = _js_base32_encode(digest)[:6]
                if expected == code_hash:
                    return True
    return False


# ── Simulación del ORDEN de validación de las 3 acciones del backend ──

def _expired(created_at: str) -> bool:
    if not created_at:
        return False
    try:
        dt = datetime.datetime.fromisoformat(created_at)
    except ValueError:
        return False
    return (datetime.datetime.now() - dt).total_seconds() > 8 * 60


def _make_row(cid="CLIENTE1", hwid="HWID1", estado="disponible",
              max_apps=3, created_at=None, served=None):
    return {
        "id": cid,
        "hwid": hwid,
        "estado": estado.upper(),
        "max_apps": max_apps,
        "created_at": created_at or datetime.datetime.now().isoformat(),
        "served": list(served or []),
    }


def _simulate(action, code, row, secret, request_hwid="HWID1", name="PHOTOSHOP"):
    """Réplica del flujo de validación (firma → expira → estado → hwid → límite)."""
    if row is None:
        return "not_found"
    row = deepcopy(row)
    cid = row["id"]
    hid = row["hwid"] or request_hwid
    if not _js_signature_valid(code, cid, hid, secret):
        return "firma_invalida"
    if _expired(row["created_at"]):
        return "expirado"
    if row["estado"] == "USADO" and action != "check_code":
        return "usado"
    if row["hwid"] and row["hwid"] != request_hwid:
        return "otro_equipo"
    if action == "get_link":
        name_key = name.upper()
        if name_key not in row["served"]:
            max_apps = row["max_apps"]
            if max_apps is not None and max_apps >= 1 and len(row["served"]) >= max_apps:
                return "limite_alcanzado"
    return "disponible"


# ── Tests de paridad con el generador del cliente ──────────────────────

@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv("SYOPS_ACTIVATION_SECRET", TEST_SECRET)
    return TEST_SECRET


def test_firma_acepta_codigo_generado(secret_env):
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _js_signature_valid(code, "CLIENTE1", "HWID1", TEST_SECRET) is True


def test_firma_rechaza_secret_distinto(secret_env):
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _js_signature_valid(code, "CLIENTE1", "HWID1", "otro-secret") is False


def test_firma_rechaza_hwid_distinto(secret_env):
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _js_signature_valid(code, "CLIENTE1", "HWID2", TEST_SECRET) is False


def test_firma_rechaza_hash_alterado(secret_env):
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    tampered = code[:4] + ("X" if code[4] != "X" else "Y") + code[5:]
    assert _js_signature_valid(tampered, "CLIENTE1", "HWID1", TEST_SECRET) is False


def test_firma_rechaza_formato_invalido(secret_env):
    for bad in ("", "ABCD", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "1234567890"):
        assert _js_signature_valid(bad, "CLIENTE1", "HWID1", TEST_SECRET) is False


# ── Simulación de las 3 acciones y el orden de capas ──────────────────

def test_check_code_firma_anula_estado(secret_env):
    """La capa 1 va PRIMERO: un código mal firmado se rechaza aunque la fila
    ya esté 'usado' (no se puede jugar con el estado para colar un código)."""
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    tampered = "ZZZZ" + code[4:]
    row = _make_row(estado="usado")
    assert _simulate("check_code", tampered, row, TEST_SECRET) == "firma_invalida"


def test_check_code_disponible(secret_env):
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _simulate("check_code", code, _make_row(), TEST_SECRET) == "disponible"


def test_get_link_respeta_max_apps(secret_env):
    """El límite de apps se cuenta server-side usando la lista `served`."""
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1",
                                               max_apps=1, secret=TEST_SECRET)
    row = _make_row(max_apps=1, served=["LIGHTROOM"])
    # Ya se sirvió 1 app (max 1): una nueva app distinta se rechaza.
    assert _simulate("get_link", code, row, TEST_SECRET, name="PHOTOSHOP") == "limite_alcanzado"
    # La app ya servida se puede volver a pedir.
    assert _simulate("get_link", code, row, TEST_SECRET, name="LIGHTROOM") == "disponible"
    # Con cupo libre, se sirve.
    assert _simulate("get_link", code, _make_row(max_apps=3), TEST_SECRET, name="PHOTOSHOP") == "disponible"


def test_get_link_codigo_invalido_en_fila_existente(secret_env):
    """Un código inventado en una fila existente se rechaza igual (doble capa)."""
    row = _make_row()
    assert _simulate("get_link", "ABC" + "D" * 7, row, TEST_SECRET) == "firma_invalida"


def test_get_link_orden_estado_expira_otro_hwid(secret_env):
    row = _make_row(estado="usado")
    assert _simulate("get_link", "ABCDEFGHIJ", row, "x") == "firma_invalida"  # capa 1 primero
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _simulate("get_link", code, _make_row(estado="usado"), TEST_SECRET) == "usado"
    assert _simulate("get_link", code, _make_row(created_at=(datetime.datetime.now() - datetime.timedelta(minutes=9)).isoformat()), TEST_SECRET) == "expirado"
    assert _simulate("get_link", code, _make_row(), TEST_SECRET, request_hwid="OTRA-PC") == "otro_equipo"


# ── Tests contra la función REAL del Apps Script (requiere Node) ───────

needs_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está disponible en PATH",
)


def _run_js_signature_check(code, cid, hid):
    proc = subprocess.run(
        ["node", str(HELPER), str(JS_PATH), TEST_SECRET, code, cid, hid],
        capture_output=True, text=True, timeout=30,
    )
    return proc.stdout.strip()


@needs_node
def test_node_valida_codigo_python(secret_env):
    """La firma del generador Python es aceptada por la función JS real."""
    if not JS_PATH.exists():
        pytest.skip("google_apps_script.js no está en el repo")
    code = activation.generate_activation_code("CLIENTE1", hwid="HWID1", secret=TEST_SECRET)
    assert _run_js_signature_check(code, "CLIENTE1", "HWID1") == "VALID"
    assert _run_js_signature_check(code, "CLIENTE1", "HWID2") == "INVALID"
    assert _run_js_signature_check(code, "CLIENTE2", "HWID1") == "INVALID"
    tampered = code[:4] + ("X" if code[4] != "X" else "Y") + code[5:]
    assert _run_js_signature_check(tampered, "CLIENTE1", "HWID1") == "INVALID"