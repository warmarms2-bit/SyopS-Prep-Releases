"""Fuerza el escenario "sin resolver_pack" en un subprocess aislado.

El entorno de dev trae resolver_pack, así que los tests de la rama pública
(marcados SKIP_WITH_PACK en test_resolver_gateway.py) quedan skipped en la
corrida normal. Este wrapper los ejecuta con SYOPS_NO_RESOLVER_PACK=1 para
verificar que la rama pública (instalación real / one-liner) sigue verde en
ambos mundos.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SIN_PACK_TESTS = (
    "test_get_resolver_sin_pack_callback",
    "test_has_resolver_sin_pack",
    "test_detectores_publicos",
)


def _run_sin_pack():
    env = dict(os.environ)
    env["SYOPS_NO_RESOLVER_PACK"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_resolver_gateway.py", "-v"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_rama_publica_sin_pack_pasa():
    proc = _run_sin_pack()
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    for t in SIN_PACK_TESTS:
        assert f"{t} PASSED" in out, out