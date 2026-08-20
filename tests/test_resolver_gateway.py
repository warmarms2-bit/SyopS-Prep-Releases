"""Tests de la activación lazy por app (services/resolver_gateway.py).

El servidor indica qué resolver usa cada app (campo `resolver`) y el
wizard activa SOLO ese resolver vía get_resolver(kind). Este módulo
verifica el contrato del gateway en ambos escenarios:
  - con resolver_pack presente (bundle del cliente)
  - sin resolver_pack (repo público / CI)
"""

import pytest

from services import resolver_gateway as g

REQUIRES_PACK = pytest.mark.skipif(
    not g.HAS_RESOLVER_PACK, reason="requiere resolver_pack privado"
)
SKIP_WITH_PACK = pytest.mark.skipif(
    g.HAS_RESOLVER_PACK, reason="solo valida cuando NO hay resolver_pack"
)


def test_kinds_estandar():
    """Los kinds conocidos deben existir en el registro."""
    for kind in ("akirabox", "swisstransfer", "workupload",
                 "pixeldrain", "seyarabata", "appstorrent"):
        assert kind in g.RESOLVER_KINDS


@REQUIRES_PACK
def test_get_resolver_activa_solo_el_kind():
    """Con el pack, get_resolver(kind) devuelve un callback invocable."""
    cb = g.get_resolver("pixeldrain", link="https://pixeldrain.com/u/AbCdEf9")
    assert callable(cb)
    url, meta = cb()
    assert url.startswith("https://") and "AbCdEf9" in url


@REQUIRES_PACK
def test_get_resolver_desconocido_raise():
    """Un kind no registrado lanza ValueError."""
    with pytest.raises(ValueError):
        g.get_resolver("dropbox", link="https://dropbox.com/x")


@REQUIRES_PACK
def test_has_resolver_con_pack():
    assert g.has_resolver("akirabox") is True
    assert g.has_resolver("dropbox") is False


@SKIP_WITH_PACK
def test_get_resolver_sin_pack_callback():
    """Sin el pack, todos los kinds devuelven un callback invocable.

    AkiraBox/Appstorrent corren su worker QWebEngine en un subprocess
    (services/*_resolver*.py), no dependen de resolver_pack.
    """
    for kind in ("pixeldrain", "swisstransfer", "workupload",
                 "seyarabata", "akirabox", "appstorrent"):
        cb = g.get_resolver(kind, link="https://example.com/x",
                            app="Test App", dest_dir="/tmp")
        assert callable(cb)


@SKIP_WITH_PACK
def test_has_resolver_sin_pack():
    """Sin el pack, todos los kinds públicos están disponibles."""
    for kind in ("pixeldrain", "swisstransfer", "workupload",
                 "seyarabata", "akirabox", "appstorrent"):
        assert g.has_resolver(kind) is True
    assert g.has_resolver("dropbox") is False


def test_resolver_hint_tolerante_a_case_y_espacios():
    """El hint del sheet tolera mayúsculas y espacios externos."""
    assert g.has_resolver(" Pixeldrain ") is True
    assert g.has_resolver("PIXELDRAIN") is True
    assert g.has_resolver("workUpload") is True
    assert g.has_resolver("  ") is False
    assert g.get_resolver(" Seyarabata ", link="https://example.com/x",
                          app="X", dest_dir="/tmp") is not None


@SKIP_WITH_PACK
def test_detectores_publicos():
    """Detección de URL de los resolvers nuevos sin el pack."""
    from services import public_resolvers as pub
    assert pub.is_akirabox_url("https://akirabox.com/abc123/file")
    assert pub.is_akirabox_url("https://akirabox.to/abc123/file")
    assert not pub.is_akirabox_url("https://pixeldrain.com/u/x")
    assert pub.is_appstorrent_url("https://appstorrent.ru/index.php?do=download&id=19")
    assert not pub.is_appstorrent_url("https://workupload.com/file/x")
    for detector, factory in pub.URL_RESOLVERS:
        assert callable(detector) and callable(factory)