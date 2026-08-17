from catalog.base import IS_MAC

_DOWNLOAD_URLS_MAC = {
    "Mole + Talon":      "combo",
    # Office: URLs directas de Microsoft para macOS (sub-apps individuales)
    "Word":              "",
    "Excel":             "",
    "PowerPoint":        "",
    "Outlook":           "",
    "OneNote":           "",
    "Microsoft AutoUpdate (MAU)": "",
    "Microsoft Office LTSC 2024 VL Serializer": "",
    "DaVinci Resolve": "",
    "Ableton Live": "",
    "FL Studio": "",
    # ── Apps nuevas (GHQ extraction 2026-08-07) ──
    # ⚠ ARQUITECTURA: estos links se asumen para ARM (Apple Silicon) por
    #   falta de especificación en el documento fuente. NO se confirmó si
    #   sirven para Intel. Antes de liberar, verificar cada link con un
    #   equipo Intel o confirmar la arquitectura de cada binario.
    #   (Ver catálogo/adobe.py: las apps Adobe ya distinguen arm/intel.)
    "Archicad":           "",
    "SketchUp Pro":       "",
    "Fusion Studio":      "",
    "FxFactory":          "",
    "ZBrush":             "",
    "Maxon License":      "",  # dep de ZBrush, no seleccionable
    "Topaz Gigapixel Pro": "",
    "Topaz Photo Pro":    "",
    "Topaz Video Pro":    "",
    "Premiere Rush":      "",
    "Apple Creator Studio": "",
    "Apple Final Cut Pro": "",
    "Apple Final Cut Pro CS": "",
    "Apple Pro Bundle":   "",
    "Logic Pro":          "",
    "Logic Pro CS":       "",
    "Cubase Pro":         "",
    "Dorico Pro":         "",
    "GrooveAgent":        "",
    "Nuendo":             "",
    "SpectraLayers Pro":  "",
    "VST Live Pro":       "",
    "WaveLab Pro":        "",

    "Blender": "",
    "AutoCAD": "",
    "CorelDRAW": "",
}

_DOWNLOAD_URLS_WIN = {
    "Mole + Talon":      "combo",
    "Mole":              "",
    "SimpleWall":        "",
    # Office: sin links para Windows (a completar en el futuro)
    # Al activar una app (cambiar None por "http" arriba),
    # descomentar su linea y poner la URL directa:
    # "DaVinci Resolve": "",
    # "FL Studio":     "",
    # "Ableton Live":  "",
    # "Revit":         "",
    # "SketchUp":      "",
    # "CorelDRAW":     "",
    # "Word":          "",
    # "Excel":         "",
    # "PowerPoint":    "",
    # "Outlook":       "",
    # "OneNote":       "",

    "Blender": "",
}

DOWNLOAD_URLS = _DOWNLOAD_URLS_MAC if IS_MAC else _DOWNLOAD_URLS_WIN
# ── MAGNET LINKS PARA DESCARGA POR TORRENT ──────────────────────
# Requisito: la app debe tener DOWNLOAD_METHODS[app] == "torrent".
# Formato: magnet:?xt=urn:btih:HASH&dn=Nombre
# Ejemplo:
#   "Photoshop": ""
# Si un magnet esta vacio (""), la app se omite en la descarga.
_TORRENT_MAGNETS_WIN = {
    "Illustrator": "",
    "Premiere Pro": "",
}

_TORRENT_MAGNETS_MAC = {
    # Sin magnets de Adobe para macOS por ahora.
}

TORRENT_MAGNETS = _TORRENT_MAGNETS_MAC if IS_MAC else _TORRENT_MAGNETS_WIN
# ── LINKS PARA DESCARGA VÍA TORBOX (debrid) ─────────────────────
# Si TORBOX_ENABLED = True, estas apps usan TorBox en vez de torrent/http.
# Se heredan de TORRENT_MAGNETS y DOWNLOAD_URLS automáticamente si no se definen aquí.
TORBOX_LINKS = {
    # "Illustrator": "",
    # "Photoshop":  "",
}

# ── LINKS DE FALLBACK VIA SWISSTRANSFER ──────────────────────────
# Si AkiraBox falla, se intenta SwissTransfer como fuente alternativa.
SWISSTRANSFER_URLS = {
    "DaVinci Resolve": "",
}
