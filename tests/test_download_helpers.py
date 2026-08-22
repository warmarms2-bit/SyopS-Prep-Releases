"""Tests de utilidades de descarga (services/http_utils.py + gateway)."""

import pytest

from services.http_utils import (
    _safe_eta, _safe_pct, _format_eta,
    _guess_extension_from_url,
    _filename_from_content_disposition, _verify_file_sha256,
)
from services.resolver_gateway import (
    _pixeldrain_file_id, is_pixeldrain_url, _pixeldrain_direct_url,
    HAS_RESOLVER_PACK,
)

REQUIRES_PACK = pytest.mark.skipif(
    not HAS_RESOLVER_PACK, reason="requiere resolver_pack privado"
)


def test_safe_pct():
    assert _safe_pct(50) == 50
    assert _safe_pct(-10) == 0
    assert _safe_pct(150) == 100
    assert _safe_pct(0) == 0


def test_safe_eta():
    assert _safe_eta(-1) == 0
    assert _safe_eta(0) == 0
    assert _safe_eta(60) == 60


def test_format_eta():
    assert _format_eta(0) == "0s"
    assert _format_eta(65) == "1m 5s"
    assert _format_eta(3600) == "1h 0m"


@REQUIRES_PACK
def test_pixeldrain_file_id():
    url = "https://pixeldrain.com/u/AbCdEf9"
    assert _pixeldrain_file_id(url) == "AbCdEf9"


@REQUIRES_PACK
def test_is_pixeldrain_url():
    assert is_pixeldrain_url("https://pixeldrain.com/u/AbCdEf9")
    assert not is_pixeldrain_url("https://example.com/file")


@REQUIRES_PACK
def test_pixeldrain_direct_url():
    url = "https://pixeldrain.com/u/AbCdEf9"
    direct = _pixeldrain_direct_url(url)
    assert "AbCdEf9" in direct
    assert direct.startswith("https")


def test_guess_extension():
    assert _guess_extension_from_url("https://x.com/file.dmg") == ".dmg"
    assert _guess_extension_from_url("https://x.com/archivo.zip?x=1") == ".zip"


def test_filename_from_content_disposition():
    header = 'attachment; filename="Blender.dmg"'
    assert _filename_from_content_disposition(header) == "Blender.dmg"
    assert _filename_from_content_disposition("") == ""


def test_verify_sha256(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"hello world")
    import hashlib
    digest = hashlib.sha256(b"hello world").hexdigest()
    assert _verify_file_sha256(f, digest)
    assert not _verify_file_sha256(f, "a" * 64)