"""Tests del auto-cleanup de Gatekeeper (system/gatekeeper.py)."""

import shutil
import subprocess
from pathlib import Path

from system import gatekeeper as gk


def _make_bundle_with_quarantine(tmp_path):
    """Copia el bundle dist y le pone cuarentena. Devuelve el path."""
    src = Path("dist/SyopS_Prep.app")
    if not src.exists():
        return None
    dst = tmp_path / "SyopS_Prep.app"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.log"))
    subprocess.run(["xattr", "-w", "com.apple.quarantine", "test", str(dst)],
                   capture_output=True)
    return dst


def test_has_quarantine(tmp_path):
    """Detecta el atributo com.apple.quarantine en un bundle."""
    bundle = _make_bundle_with_quarantine(tmp_path)
    if not bundle:
        return  # sin bundle en dist (CI)
    assert gk._has_quarantine(bundle)


def test_cleanup_removes_quarantine(tmp_path):
    """_cleanup_bundle elimina la cuarentena y re-firma ad-hoc."""
    bundle = _make_bundle_with_quarantine(tmp_path)
    if not bundle:
        return
    assert gk._cleanup_bundle(bundle)
    assert not gk._has_quarantine(bundle)


def test_cleanup_sin_cuarentena(tmp_path):
    """Un bundle sin cuarentena se mantiene limpio."""
    src = Path("dist/SyopS_Prep.app")
    if not src.exists():
        return
    dst = tmp_path / "SyopS_Prep.app"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.log"))
    assert not gk._has_quarantine(dst)
    assert gk._cleanup_bundle(dst)
    assert not gk._has_quarantine(dst)
