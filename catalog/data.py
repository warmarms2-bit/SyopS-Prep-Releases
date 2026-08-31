"""
Re-export de los sub-módulos cohesivos de catalog/. Mantiene la
compatibilidad con los imports históricos desde catalog.data.
"""

from catalog.base import IS_MAC, IS_WIN, GB
from catalog.categorias import (
    CATEGORY_META, APP_CATEGORY, _build_software_categories,
    SOFTWARE_CATEGORIES, OFFICE_PARENT, OFFICE_APPS, OFFICE_CORE_APPS,
    _expand_office_for_downloads, _expand_office_for_display,
)
from catalog.adobe import (
    ADOBE_METHODS, ADOBE_APPS, ADOBE_FULL_PACK_APPS, ADOBE_FULL_PACK_COLLECTION,
    ADOBE_AIO_MACKED_LINKS, ADOBE_AIO_SICE_LINKS, ADOBE_MULTILANG_LINKS,
    ADOBE_PATCHERS_SICE, ADOBE_ACTIVATION_TOOL_LINKS, ADOBE_TOOLS,
    ADOBE_APPS_PER_CREDIT,
)
from catalog.specs import (
    APP_SPECS, INSTALL_INSTRUCTIONS, DOWNLOAD_METHODS, INSTALL_QUESTIONS,
)
from catalog.urls import (
    _DOWNLOAD_URLS_MAC, _DOWNLOAD_URLS_WIN, DOWNLOAD_URLS,
    _TORRENT_MAGNETS_MAC, _TORRENT_MAGNETS_WIN, TORRENT_MAGNETS,
    TORBOX_LINKS, SWISSTRANSFER_URLS,
)
from catalog.tools import (
    COMBO_TOOLS, TOOL_APPS, _expand_apps, TOOL_DESCS, APP_TOOLS,
    _app_tools_for_app, _all_app_tools, _apps_with_tools, sheet_tool_metodos,
)

__all__ = [
    "IS_MAC", "IS_WIN", "GB",
    "CATEGORY_META", "APP_CATEGORY", "_build_software_categories",
    "SOFTWARE_CATEGORIES", "OFFICE_PARENT", "OFFICE_APPS", "OFFICE_CORE_APPS",
    "_expand_office_for_downloads", "_expand_office_for_display",
    "ADOBE_METHODS", "ADOBE_APPS", "ADOBE_FULL_PACK_APPS", "ADOBE_FULL_PACK_COLLECTION",
    "ADOBE_AIO_MACKED_LINKS", "ADOBE_AIO_SICE_LINKS", "ADOBE_MULTILANG_LINKS",
    "ADOBE_PATCHERS_SICE", "ADOBE_ACTIVATION_TOOL_LINKS", "ADOBE_TOOLS",
    "ADOBE_APPS_PER_CREDIT",
    "APP_SPECS", "INSTALL_INSTRUCTIONS", "DOWNLOAD_METHODS", "INSTALL_QUESTIONS",
    "_DOWNLOAD_URLS_MAC", "_DOWNLOAD_URLS_WIN", "DOWNLOAD_URLS",
    "_TORRENT_MAGNETS_MAC", "_TORRENT_MAGNETS_WIN", "TORRENT_MAGNETS",
    "TORBOX_LINKS", "SWISSTRANSFER_URLS",
    "COMBO_TOOLS", "TOOL_APPS", "_expand_apps", "TOOL_DESCS", "APP_TOOLS",
    "_app_tools_for_app", "_all_app_tools", "_apps_with_tools", "sheet_tool_metodos",
]
