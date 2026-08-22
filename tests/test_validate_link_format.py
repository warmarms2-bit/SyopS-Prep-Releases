"""
Tests para _validate_link_format: runtime format validation de method↔link.

Verifica que el método declarado coincida con el formato real del link,
atrapando errores de configuración antes de que lleguen al motor de descarga
o a los resolvers de URL.

Cubre:
  - method=torrent con link http (el caso crítico que enmascaraba éxito)
  - method=http con link magnet
  - method=torbox aceptando ambos formatos
  - method=group/combo/manual (sin validación, siempre None)
  - link vacío (manejado aparte, no es un problema de formato)
"""

import pytest

from services.download_resolvers import _validate_link_format  # noqa: E402
from services.resolver_gateway import (  # noqa: E402
    URL_RESOLVERS, is_pixeldrain_url, HAS_RESOLVER_PACK,
)

REQUIRES_PACK = pytest.mark.skipif(
    not HAS_RESOLVER_PACK, reason="requiere resolver_pack privado"
)


class TestTorrentLinkFormat:
    """method=torrent requiere link que empiece con 'magnet:'."""

    @REQUIRES_PACK
    def test_torrent_with_pixeldrain_http_url_returns_error(self):
        """CASO CRÍTICO: link http de Pixeldrain no es un magnet.
        Sin _validate_link_format, is_pixeldrain_url(link) matchearía en
        URL_RESOLVERS y crearía un DownloadTask con method=http y
        resolver_callback — descarga silenciosa como http (éxito engañoso).
        Con la validación, esto se detecta como error de configuración."""
        link = "https://pixeldrain.com/u/AbCdEf9"
        assert is_pixeldrain_url(link), (
            "Precondición: este link debe matchear is_pixeldrain_url"
        )
        err = _validate_link_format("torrent", link)
        assert err is not None, (
            "method=torrent con link http de Pixeldrain debe devolver error, "
            "no None — sin la validación, el resolver lo descargaría como http"
        )
        assert "torrent" in err.lower()
        assert "pixeldrain" in err.lower() or "https://" in err

    def test_torrent_with_generic_http_url_returns_error(self):
        """Link http genérico (no Pixeldrain) tampoco es un magnet."""
        err = _validate_link_format(
            "torrent", "https://example.com/file.zip"
        )
        assert err is not None
        assert "magnet" in err.lower()

    def test_torrent_with_valid_magnet_returns_none(self):
        """Link magnet válido para method=torrent → sin error."""
        err = _validate_link_format(
            "torrent", "magnet:?xt=urn:btih:0b4963034c8dc84b74f1cad1c3d8239458403fe7&dn=test"
        )
        assert err is None

    def test_torrent_with_magnet_minimal_returns_none(self):
        """Magnet con prefijo mínimo → válido."""
        err = _validate_link_format("torrent", "magnet:?xt=urn:btih:abc")
        assert err is None


class TestHttpLinkFormat:
    """method=http requiere link http/https, NO magnet."""

    def test_http_with_magnet_returns_error(self):
        """Link magnet en DOWNLOAD_URLS es un error de configuración."""
        err = _validate_link_format(
            "http", "magnet:?xt=urn:btih:0b4963034c8dc84b74f1cad1c3d8239458403fe7"
        )
        assert err is not None
        assert "magnet" in err.lower()

    def test_http_with_valid_https_returns_none(self):
        """Link https válido → sin error."""
        err = _validate_link_format(
            "http", "https://officecdn.microsoft.com/pr/file.pkg"
        )
        assert err is None

    def test_http_with_valid_http_returns_none(self):
        """Link http (sin s) válido → sin error."""
        err = _validate_link_format(
            "http", "http://example.com/file.zip"
        )
        assert err is None

    def test_http_with_ftp_returns_error(self):
        """Link ftp no es http ni magnet → error."""
        err = _validate_link_format(
            "http", "ftp://example.com/file.zip"
        )
        assert err is not None
        assert "http" in err.lower()


class TestTorboxLinkFormat:
    """method=torbox acepta magnet O http/https."""

    def test_torbox_with_magnet_returns_none(self):
        """Torbox acepta magnet."""
        err = _validate_link_format(
            "torbox", "magnet:?xt=urn:btih:abc"
        )
        assert err is None

    def test_torbox_with_https_returns_none(self):
        """Torbox acepta https."""
        err = _validate_link_format(
            "torbox", "https://example.com/file.zip"
        )
        assert err is None

    def test_torbox_with_ftp_returns_error(self):
        """Torbox NO acepta ftp."""
        err = _validate_link_format(
            "torbox", "ftp://example.com/file.zip"
        )
        assert err is not None


class TestNoValidationMethods:
    """manual, group, combo no se validan (siempre None)."""

    @pytest.mark.parametrize("method", ["manual", "group", "combo"])
    def test_no_validation_returns_none(self, method):
        """Estos métodos no llegan con link real a _validate_link_format."""
        err = _validate_link_format(method, "cualquier_cosa")
        assert err is None

    def test_none_method_returns_none(self):
        """None como method no se valida."""
        err = _validate_link_format(None, "cualquier_cosa")
        assert err is None


class TestEdgeCases:
    """Casos borde."""

    def test_empty_link_returns_none(self):
        """Link vacío no es un problema de FORMATO (se maneja aparte)."""
        err = _validate_link_format("torrent", "")
        assert err is None

    def test_empty_link_http_returns_none(self):
        err = _validate_link_format("http", "")
        assert err is None

    def test_error_message_truncates_long_link(self):
        """Link muy largo se trunca a 80 chars + '...'."""
        long_link = "https://example.com/" + "a" * 200
        err = _validate_link_format("torrent", long_link)
        assert err is not None
        assert "..." in err
        assert long_link not in err  # link completo no está en el mensaje
        assert len(err) < 200  # mensaje razonablemente corto

    def test_error_message_contains_method_and_link_prefix(self):
        """El mensaje debe indicar el method y el prefijo del link."""
        err = _validate_link_format(
            "torrent", "https://pixeldrain.com/u/AbCdEf9"
        )
        assert err is not None
        assert "torrent" in err
        assert "https://pixeldrain" in err

    @REQUIRES_PACK
    def test_url_resolvers_would_match_critical_link(self):
        """Precondición del caso crítico: el link de Pixeldrain matchea
        al menos un detector en URL_RESOLVERS. Si esto falla, el caso
        crítico no es tal (ningún resolver lo capturaría)."""
        link = "https://pixeldrain.com/u/AbCdEf9"
        matched = any(det(link) for det, _fac in URL_RESOLVERS)
        assert matched, (
            "El link de Pixeldrain debe matchear al menos un resolver "
            "para que el caso crítico sea relevante"
        )
