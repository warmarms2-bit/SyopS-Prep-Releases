"""Tests del sistema de activación por código (services/activation.py)."""

import os
import tempfile
from pathlib import Path

import pytest

from services import activation


TEST_SECRET = "test-secret-para-tests-1234567890abcdef"


@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv("SYOPS_ACTIVATION_SECRET", TEST_SECRET)
    return TEST_SECRET


def test_secret_requerido():
    """Sin SYOPS_ACTIVATION_SECRET, _get_secret() lanza error explícito."""
    os.environ.pop("SYOPS_ACTIVATION_SECRET", None)
    with pytest.raises(RuntimeError):
        activation._get_secret()


def test_generar_codigo_valido(secret_env):
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1")
    assert len(code) == activation.CODE_LENGTH
    assert code.isalnum()
    assert code.isupper()


def test_generar_con_secret_explicito():
    """Se puede inyectar secret directamente (sin depender de env)."""
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1", secret=TEST_SECRET)
    assert len(code) == activation.CODE_LENGTH


def test_verificar_codigo_correcto(secret_env):
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1", max_apps=3)
    max_apps = activation.get_activation_max_apps("CLIENT1", code, hwid="HWID1")
    assert max_apps == 3


def test_codigo_invalido_rechazado(secret_env):
    max_apps = activation.get_activation_max_apps("CLIENT1", "INVALID1234", hwid="HWID1")
    assert max_apps == 0


def test_codigo_vinculado_a_hwid(secret_env):
    """El código generado para HWID1 no funciona en HWID2."""
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1")
    max_apps = activation.get_activation_max_apps("CLIENT1", code, hwid="HWID2")
    assert max_apps == 0


def test_codigo_vinculado_a_client(secret_env):
    """El código generado para CLIENT1 no funciona en CLIENT2."""
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1")
    max_apps = activation.get_activation_max_apps("CLIENT2", code, hwid="HWID1")
    assert max_apps == 0


def test_secret_distinto_invalida_codigo():
    """Un código generado con un secret no verifica con otro secret."""
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1", secret="secret-A")
    max_apps = activation.get_activation_max_apps(
        "CLIENT1", code, hwid="HWID1", secret="secret-B"
    )
    assert max_apps == 0


def test_estado_guardado_y_marcado_usado():
    """save/load/is_activated/mark_activation_used funcionan con dir temporal."""
    tmp = Path(tempfile.mkdtemp())
    # Guardar con un código generado con el secret de test
    code = activation.generate_activation_code("CLIENT1", hwid="HWID1", secret=TEST_SECRET)
    activation.save_activation_state(tmp, "CLIENT1", code, 3, hwid="HWID1")
    assert activation.is_activated(tmp, "CLIENT1", hwid="HWID1", secret=TEST_SECRET)
    activation.mark_activation_used(tmp, "CLIENT1", hwid="HWID1")
    assert not activation.is_activated(tmp, "CLIENT1", hwid="HWID1", secret=TEST_SECRET)


def test_codigo_expira():
    """Código con fecha de creación antigua se considera expirado."""
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(minutes=30)).isoformat()
    assert activation._is_activation_expired(old)


def test_codigo_reciente_no_expirado():
    from datetime import datetime
    recent = datetime.now().isoformat()
    assert not activation._is_activation_expired(recent)
