#!/usr/bin/env python3
"""
Sistema de activación por código para SyopS Prep.

Recomendación práctica implementada:
  1. Vinculación al equipo: cada código se genera con el HWID del equipo y
     solo es válido en ese equipo.
  2. Un solo uso: una vez completado el servicio se marca el código como
     usado localmente (y en el backend cuando esté disponible). No se puede
     reactivar la descarga con el mismo código después de terminar.

El código tiene 10 caracteres alfanuméricos (base32): 4 de nonce + 6 de HMAC.
El nonce lo hace único y de un solo uso, y permite verificarlo sin depender
exclusivamente del backend.

El operador genera el código con el script generate_activation_code.py,
usando el client_id y el HWID que el cliente envía por WhatsApp.
"""
import hmac
import hashlib
import base64
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

CODE_LENGTH = 10
NONCE_LENGTH = 4
HASH_LENGTH = 6

# Vida útil de un código de activación desde su generación (en minutos).
# Debe coincidir con CODE_LIFETIME_MINUTES de google_apps_script.js.
CODE_LIFETIME_MINUTES = 8


def _get_secret() -> str:
    """Devuelve el secret de activación desde la variable de entorno.

    Sin secret configurado el sistema de licencias no puede funcionar de
    forma segura: lanza RuntimeError en lugar de usar un default débil
    (que comprometería la emisión de códigos). Configurar
    SYOPS_ACTIVATION_SECRET antes de generar o verificar códigos.
    """
    secret = os.environ.get("SYOPS_ACTIVATION_SECRET")
    if not secret:
        raise RuntimeError(
            "SYOPS_ACTIVATION_SECRET no está configurado. El sistema de "
            "activación requiere un secret explícito (ver docs)."
        )
    return secret


def _is_activation_expired(created_at_str: str) -> bool:
    if not created_at_str:
        return True
    try:
        created_at = datetime.fromisoformat(created_at_str)
    except Exception:
        return True
    if (datetime.now() - created_at).total_seconds() > CODE_LIFETIME_MINUTES * 60:
        return True
    return False


def _normalize_client_id(client_id: str) -> str:
    return (client_id or "").strip().upper()


def _normalize_hwid(hwid: str) -> str:
    return (hwid or "").strip().upper()


def _generate_nonce() -> str:
    # 4 caracteres base32 ~ 20 bits de aleatoriedad, suficiente para un solo uso.
    return base64.b32encode(secrets.token_bytes(3)).decode("ascii")[:NONCE_LENGTH].upper()


def _hash_code(nonce: str, client_id: str, hwid: str, max_apps: int,
               period: str, valid_days: int, secret: str) -> str:
    hwid_part = hwid if hwid else "NOHWID"
    payload = f"{nonce}:{client_id}:{hwid_part}:{max_apps}:{period}:{valid_days}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.b32encode(digest).decode("ascii")[:HASH_LENGTH].upper()


def generate_activation_code(client_id: str, hwid: str = None, secret: str = None,
                             max_apps: int = 3, valid_days: int = 7) -> str:
    """
    Genera un código de activación de 10 caracteres alfanuméricos en mayúsculas.

    El código depende de:
      - client_id
      - HWID del equipo (vincula el código a ese equipo)
      - max_apps permitidas
      - secreto compartido
      - periodo de validez (semana calendario)
      - nonce aleatorio (lo hace único y de un solo uso)
    """
    if secret is None:
        secret = _get_secret()
    cid = _normalize_client_id(client_id)
    if not cid:
        raise ValueError("client_id no puede estar vacío")
    hid = _normalize_hwid(hwid)
    if not hid:
        raise ValueError("hwid no puede estar vacío")
    max_apps = max(1, min(int(max_apps), 99))

    today = datetime.now()
    year, week, _ = today.isocalendar()
    period = f"{year}-W{week}"

    nonce = _generate_nonce()
    code_hash = _hash_code(nonce, cid, hid, max_apps, period, valid_days, secret)
    return nonce + code_hash


def generate_activation_code_full_pack(client_id: str, hwid: str = None, secret: str = None,
                                       valid_days: int = 7) -> str:
    """
    Genera un código de activación para el Adobe Full Pack.
    Usa max_apps=99 para distinguirse de los códigos normales (1 o 3 apps).
    """
    return generate_activation_code(client_id, hwid=hwid, secret=secret,
                                    max_apps=99, valid_days=valid_days)


def get_activation_type(syops_dir: Path, client_id: str, hwid: str = None) -> str:
    """
    Retorna el tipo de activación guardada: 'standard' o 'adobe_full_pack'.
    """
    saved_id, _, _, saved_hwid, used, type_value, created_at = load_activation_state(syops_dir)
    if not saved_id:
        return "standard"
    if _normalize_client_id(saved_id) != _normalize_client_id(client_id):
        return "standard"
    if hwid and saved_hwid and _normalize_hwid(saved_hwid) != _normalize_hwid(hwid):
        return "standard"
    if used or _is_activation_expired(created_at):
        return "standard"
    return type_value if type_value in ("standard", "adobe_full_pack") else "standard"


def _decode_activation_code(client_id: str, code: str, secret: str,
                            hwid: str = None, lookback_weeks: int = 4) -> dict:
    """
    Intenta decodificar un código probando combinaciones de periodo, max_apps,
    duración de validez y HWID. Retorna {"max_apps": int} si coincide, o None.
    """
    code = code.strip().upper()
    if len(code) != CODE_LENGTH:
        return None

    nonce = code[:NONCE_LENGTH]
    if len(nonce) != NONCE_LENGTH:
        return None
    code_hash = code[NONCE_LENGTH:]

    cid = _normalize_client_id(client_id)
    if not cid:
        return None
    hid = _normalize_hwid(hwid)

    today = datetime.now()
    for i in range(lookback_weeks + 1):
        dt = today - timedelta(weeks=i)
        year, week, _ = dt.isocalendar()
        period = f"{year}-W{week}"
        for max_apps in (1, 3, 99):
            for valid_days in (7, 30, 365):
                if not hid:
                    return None
                expected = _hash_code(nonce, cid, hid, max_apps,
                                      period, valid_days, secret)
                if hmac.compare_digest(expected, code_hash):
                    return {"max_apps": max_apps}
    return None


def verify_activation_code(client_id: str, code: str, hwid: str = None,
                           secret: str = None, lookback_weeks: int = 4) -> bool:
    """
    Verifica si un código de activación es válido para el client_id y HWID.
    """
    if not code or not isinstance(code, str):
        return False
    if secret is None:
        secret = _get_secret()
    return _decode_activation_code(client_id, code, secret, hwid, lookback_weeks) is not None


def get_activation_max_apps(client_id: str, code: str, hwid: str = None,
                            secret: str = None, lookback_weeks: int = 4) -> int:
    """
    Retorna la cantidad de apps permitidas por el código, o 0 si es inválido.
    """
    if not code or not isinstance(code, str):
        return 0
    if secret is None:
        secret = _get_secret()
    decoded = _decode_activation_code(client_id, code, secret, hwid, lookback_weeks)
    return decoded.get("max_apps", 0) if decoded else 0


def _state_file_path(syops_dir: Path) -> Path:
    return Path(syops_dir) / ".activated"


def save_activation_state(syops_dir: Path, client_id: str, code: str,
                          max_apps: int = 3, hwid: str = None, used: bool = False,
                          type_value: str = "standard", created_at: str = None) -> bool:
    """
    Guarda un archivo local con la activación, incluyendo max_apps, HWID, uso, type y created_at.
    """
    try:
        state_file = _state_file_path(syops_dir)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        if created_at is None:
            created_at = datetime.now().isoformat()
        lines = [
            _normalize_client_id(client_id),
            code.strip().upper(),
            str(max_apps),
            _normalize_hwid(hwid),
            "1" if used else "0",
            (type_value or "standard").strip().lower(),
            created_at,
        ]
        state_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def load_activation_state(syops_dir: Path) -> tuple:
    """
    Lee el estado de activación guardado.
    Retorna (client_id, code, max_apps, hwid, used, type, created_at).
    """
    try:
        state_file = _state_file_path(syops_dir)
        if not state_file.exists():
            return None, None, 0, None, False, "standard", None
        lines = state_file.read_text(encoding="utf-8").strip().splitlines()
        client_id = lines[0].strip() if len(lines) > 0 else None
        code = lines[1].strip() if len(lines) > 1 else None
        try:
            max_apps = int(lines[2].strip()) if len(lines) > 2 else 3
        except Exception:
            max_apps = 3
        hwid = lines[3].strip() if len(lines) > 3 else None
        used = False
        if len(lines) > 4:
            used = lines[4].strip() in ("1", "true", "True", "TRUE", "yes", "si", "Si")
        type_value = lines[5].strip().lower() if len(lines) > 5 else "standard"
        created_at = lines[6].strip() if len(lines) > 6 else None
        return client_id, code, max_apps, hwid, used, type_value, created_at
    except Exception:
        return None, None, 0, None, False, "standard", None


def is_activated(syops_dir: Path, client_id: str, hwid: str = None,
                 secret: str = None) -> bool:
    """
    Comprueba si hay una activación guardada válida para este equipo.

    La autoridad de activación es el backend (Google Sheets): la app solo
    guarda localmente un código que el servidor ya confirmó. Por eso esta
    verificación NO requiere el secret (HMAC): se limita a validar que el
    estado local exista, corresponda a este equipo y no esté usado/expirado.
    El backend re-valida el código de forma asíncrona al arrancar
    (sync_local_activation_with_backend) y borra el estado si ya no vale.
    """
    saved_id, saved_code, _, saved_hwid, used, _, created_at = load_activation_state(syops_dir)
    if not saved_id or not saved_code:
        return False
    if used or _is_activation_expired(created_at):
        return False
    if _normalize_client_id(saved_id) != _normalize_client_id(client_id):
        return False
    if hwid and saved_hwid and _normalize_hwid(saved_hwid) != _normalize_hwid(hwid):
        return False
    return True


def get_activated_max_apps(syops_dir: Path, client_id: str, hwid: str = None,
                           secret: str = None) -> int:
    """
    Retorna la cantidad de apps permitidas por la activación guardada, o 0 si
    no está activada, si el código ya fue usado o si expiró.

    max_apps lo asigna el backend al confirmar el código; se guarda en el
    estado local y aquí solo se lee. No requiere el secret.
    """
    saved_id, saved_code, saved_max, saved_hwid, used, _, created_at = load_activation_state(syops_dir)
    if not saved_id or not saved_code or used or _is_activation_expired(created_at):
        return 0
    if _normalize_client_id(saved_id) != _normalize_client_id(client_id):
        return 0
    if hwid and saved_hwid and _normalize_hwid(saved_hwid) != _normalize_hwid(hwid):
        return 0
    return saved_max


def mark_activation_used(syops_dir: Path, client_id: str, hwid: str = None) -> bool:
    """
    Marca la activación guardada como usada (servicio completado). Después de
    esto, el mismo código no puede reactivar la descarga en este equipo.
    """
    state = load_activation_state(syops_dir)
    if not state[0]:
        return False
    saved_id, saved_code, saved_max, saved_hwid, _, type_value, created_at = state
    if _normalize_client_id(saved_id) != _normalize_client_id(client_id):
        return False
    if hwid and saved_hwid and _normalize_hwid(saved_hwid) != _normalize_hwid(hwid):
        return False
    return save_activation_state(syops_dir, saved_id, saved_code, saved_max,
                                 saved_hwid or hwid, used=True,
                                 type_value=type_value, created_at=created_at)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python activation.py <client_id> [hwid]")
        sys.exit(1)
    cid = sys.argv[1]
    hid = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"client_id: {cid}")
    if hid:
        print(f"hwid: {hid}")
    print(f"código de activación: {generate_activation_code(cid, hwid=hid)}")
