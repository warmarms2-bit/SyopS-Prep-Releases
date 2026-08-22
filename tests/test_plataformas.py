"""Regresión del filtro de disponibilidad por plataforma (flujo original).

El cliente NO trae URLs: la compatibilidad mac/win se resuelve con la tabla
estática catalog/plataformas.py, que replica el comportamiento del catálogo
previo a la capa de reparto (no romper la selección en el cliente).
"""

import pytest

from app_flow.flujo import platform_apps
from catalog.plataformas import is_compatible


def test_windows_ve_apps_de_windows():
    """En Windows las apps de Apple/mac-only no se muestran."""
    from catalog.data import SOFTWARE_CATEGORIES
    design = SOFTWARE_CATEGORIES["graphic_design"]["apps"]
    apps = platform_apps(design, is_mac=False, is_win=True)
    assert "Illustrator" in apps
    assert "Blender" in apps
    assert "Photoshop" not in apps  # solo mac en el catálogo original
    assert "InDesign" not in apps
    assert "Dimension" not in apps


def test_macos_ve_catalogo_completo_de_diseno():
    from catalog.data import SOFTWARE_CATEGORIES
    design = SOFTWARE_CATEGORIES["graphic_design"]["apps"]
    apps = platform_apps(design, is_mac=True, is_win=False)
    assert len(apps) >= len(design) - 2  # solo se ocultan win-only (Mole/SimpleWall no están acá)
    assert "Photoshop" in apps and "Illustrator" in apps


@pytest.mark.parametrize("app,platform,expected", [
    ("Photoshop", "mac", True),
    ("Photoshop", "win", False),
    ("Illustrator", "mac", True),
    ("Illustrator", "win", True),
    ("Premiere Pro", "win", True),
    ("Blender", "win", True),
    ("Apple Final Cut Pro", "win", False),
    ("Apple Final Cut Pro", "mac", True),
    ("SimpleWall", "win", True),
    ("SimpleWall", "mac", False),
])
def test_tabla_compatibilidad(app, platform, expected):
    assert is_compatible(app, platform) is expected


def test_app_desconocida_no_se_oculta():
    """Apps agregadas después siguen visibles (default conservador)."""
    assert is_compatible("App Futura 2027", "win") is True
    assert is_compatible("App Futura 2027", "mac") is True