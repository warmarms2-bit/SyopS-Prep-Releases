# ── ADOBE: MÉTODOS, LINKS Y TOOLS (macOS) ─────────────────────────
# Métodos disponibles para instalar Adobe en macOS. El usuario puede elegir
# cualquiera, pero la app recomienda AIO MacKed como la opción más rápida.
ADOBE_METHODS = {
    "aio_macked": {
        "label": "adobe.aio_macked",
        "desc": "adobe.aio_macked_desc",
        "recommended": True,
        "warning": "adobe.aio_macked_warning",
        "bullets": ["adobe.aio_macked_bullet1", "adobe.aio_macked_bullet2", "adobe.aio_macked_bullet3"],
    },
    "aio_sice": {
        "label": "adobe.aio_sice",
        "desc": "adobe.aio_sice_desc",
        "recommended": False,
        "warning": "adobe.aio_sice_warning",
        "bullets": ["adobe.aio_sice_bullet1", "adobe.aio_sice_bullet2", "adobe.aio_sice_bullet3", "adobe.aio_sice_bullet4"],
    },
    "multilang_sice": {
        "label": "adobe.multilang_sice",
        "desc": "adobe.multilang_sice_desc",
        "recommended": False,
        "warning": "adobe.multilang_sice_warning",
        "bullets": ["adobe.multilang_sice_bullet1", "adobe.multilang_sice_bullet2", "adobe.multilang_sice_bullet3", "adobe.multilang_sice_bullet4"],
    },
    "activation_tool": {
        "label": "adobe.activation_tool",
        "desc": "adobe.activation_tool_desc",
        "recommended": False,
        "warning": "adobe.activation_tool_warning",
        "bullets": ["adobe.activation_tool_bullet1", "adobe.activation_tool_bullet2", "adobe.activation_tool_bullet3", "adobe.activation_tool_bullet4"],
    },
}

# ── LISTA DE PROGRAMAS ADOBE (para detección de software instalado) ─
ADOBE_APPS = frozenset([
    "Photoshop", "Illustrator", "Premiere Pro", "After Effects",
    "Lightroom Classic", "Acrobat Pro", "Audition", "InDesign",
    "Animate", "Bridge", "Media Encoder", "Character Animator",
    "Dreamweaver", "Dimension", "InCopy", "Substance 3D",
    "Adobe XD", "Substance 3D Designer", "Substance 3D Painter",
    "Substance 3D Sampler",
])

# Todos los programas incluidos en el Adobe Full Pack.
ADOBE_FULL_PACK_APPS = list(ADOBE_APPS)

# ── COLEECCIÓN FULL PACK (AIO MacKed) ─────────────────────────────
# Cada variante tiene {url, version}. Se elige ARM o Intel según el Mac.
ADOBE_FULL_PACK_COLLECTION = {
    "arm":   {"url": "", "version": "2026.08 v1 (Aug 2026)"},
    "intel": {"url": "", "version": "2026.08 v1 (Aug 2026)"},
    "name":  "Adobe Collection 2026.08 v1 MacKed AIO",
}

# ── LINKS POR APP CON VERSIONES ───────────────────────────────────
# Cada app es una LISTA de versiones (de la más nueva a la más vieja).
# Cada versión: {"version": str, "arm": {"url", "resolver"}, "intel": {...}}
# - url: link de vista de Pixeldrain (https://pixeldrain.com/u/<id>)
# - resolver: bypass a usar para resolver la descarga directa.
#   "pixeldrain" = API oficial (/api/file/<id>); "gamedrive" o "isuru" = bypass.
# La app descarga la versión MÁS NUEVA cuyo link esté vivo (ver link_health).

# Links AIO MacKed por app (elegir Online u Offline según preferencia).
# Se usa "offline" por defecto para evitar problemas de mezcla Online/Offline.
ADOBE_AIO_MACKED_LINKS = {
    "Acrobat Pro": [
        {"version": "26.001.21771 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "After Effects": [
        {"version": "26.3.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Animate": [
        {"version": "24.0.12 2024",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Bridge": [
        {"version": "16.0.6 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Dimension": [
        {"version": "4.1.6 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Dreamweaver": [
        {"version": "21.8 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Illustrator": [
        {"version": "30.7.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "InDesign": [
        {"version": "21.5.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Lightroom Classic": [
        {"version": "15.5.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Media Encoder": [
        {"version": "26.3.2 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Photoshop": [
        {"version": "27.9.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Premiere Pro": [
        {"version": "26.3.2 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Substance 3D": [
        {"version": "16.0.3 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Substance 3D Designer": [
        {"version": "16.0.3 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": None, "resolver": "pixeldrain"}},
    ],
    "Substance 3D Painter": [
        {"version": "12.0.2 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": None, "resolver": "pixeldrain"}},
    ],
    "Substance 3D Sampler": [
        {"version": "6.0.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": None, "resolver": "pixeldrain"}},
    ],
    "Adobe XD": [
        {"version": "59.0.12 2025",
         "arm":   {"url": None, "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
}

# Links AIO Sice por app.
ADOBE_AIO_SICE_LINKS = {
    "After Effects": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Audition": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Bridge": [
        {"version": "16.0.2 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Character Animator": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Illustrator": [
        {"version": "30.2.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "InCopy": [
        {"version": "21.2.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "InDesign": [
        {"version": "21.2.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Media Encoder": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Photoshop": [
        {"version": "27.3.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Premiere Pro": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
}

# Links de instaladores multilingües oficiales (GHQ) por app.
ADOBE_MULTILANG_LINKS = {
    "After Effects": [
        {"version": "26.3.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Audition": [
        {"version": "26.3.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Character Animator": [
        {"version": "26.0.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Dreamweaver": [
        {"version": "21.8 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Dimension": [
        {"version": "4.1.7 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "InCopy": [
        {"version": "21.5.1 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Lightroom Classic": [
        {"version": "15.5.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Media Encoder": [
        {"version": "26.3.2 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
    "Photoshop": [
        {"version": "27.8.0 2026",
         "arm":   {"url": "", "resolver": "pixeldrain"},
         "intel": {"url": "", "resolver": "pixeldrain"}},
    ],
}

# Parches Sice para el método multilingüe (versión que coincide con el installer).
ADOBE_PATCHERS_SICE = {
    "Photoshop":        "",
    "Illustrator":      "",
    "Premiere Pro":     "",
    "After Effects":    "",
    "Audition":         "",
    "Bridge":           "",
    "Character Animator":"",
    "InCopy":           "",
    "InDesign":         "",
    "Media Encoder":    "",
}

# Adobe Activation Tool (dos variantes: con cuenta / sin cuenta).
ADOBE_ACTIVATION_TOOL_LINKS = {
    "with_account":  "",
    "no_account":    "",
    "adobe_downloader": "",
}

# Tools de Adobe que se descargan automáticamente según el método elegido.
ADOBE_TOOLS = {
    "Sentinel": {
        "url": "",
        "for_methods": ["aio_macked", "aio_sice", "multilang_sice", "activation_tool"],
        "required": True,
    },
    "Adobe Genuine Pop-Up Blocker": {
        "url": "",
        "for_methods": ["aio_macked"],
        "required": True,
    },
    "AntiCC v1.7": {
        "url": "",
        "for_methods": ["multilang_sice", "activation_tool"],
        "required": True,
    },
    "Adobe ACC Runtime": {
        "url": "",
        "for_methods": ["multilang_sice", "activation_tool"],
        "required": True,
    },
    "Adobe Cleaner Tool": {
        "url": "",
        "for_methods": ["multilang_sice", "activation_tool"],
        "required": True,
    },
    "Adobe Downloader": {
        "url": "",
        "for_methods": ["activation_tool"],
        "required": True,
    },
}

# Máximo de apps de Adobe que cuentan como 1 sola app dentro del límite.
# =1 => cada app (incluida Adobe) cuenta individualmente. El límite de
# selección es estricto: 3 apps son 3, sin descuento por ser Adobe.
ADOBE_APPS_PER_CREDIT = 1
