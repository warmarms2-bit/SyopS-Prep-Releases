"""Compatibilidad por plataforma (mac/win) del catálogo.

Tabla estática derivada del estado del catálogo previo a la capa de
reparto (commit b673b77^). Reproduce el MISMO filtro del flujo original
sin exponer URLs: cada app sabe en qué SO estaba disponible.

VALORES: "mac" | "win" | "both" | "none"
"""

_APP_PLATFORMS: dict[str, str] = {
    "Ableton Live": "mac",
    "Acrobat Pro": "mac",
    "Adobe XD": "mac",
    "After Effects": "mac",
    "Animate": "mac",
    "Apple Creator Studio": "mac",
    "Apple Final Cut Pro": "mac",
    "Apple Final Cut Pro CS": "mac",
    "Apple Pro Bundle": "mac",
    "Archicad": "mac",
    "Audition": "mac",
    "AutoCAD": "mac",
    "Blender": "both",
    "Bridge": "mac",
    "Character Animator": "mac",
    "CorelDRAW": "mac",
    "Cubase Pro": "mac",
    "DaVinci Resolve": "both",
    "Dimension": "mac",
    "Dorico Pro": "mac",
    "Dreamweaver": "mac",
    "Excel": "mac",
    "FL Studio": "mac",
    "Fusion Studio": "mac",
    "FxFactory": "mac",
    "GrooveAgent": "mac",
    "Illustrator": "both",
    "InCopy": "mac",
    "InDesign": "mac",
    "Lightroom Classic": "mac",
    "Logic Pro": "mac",
    "Logic Pro CS": "mac",
    "Media Encoder": "mac",
    "Microsoft AutoUpdate (MAU)": "mac",
    "Microsoft Office LTSC 2024 VL Serializer": "mac",
    "Mole": "win",
    "Mole + Talon": "none",
    "Nuendo": "mac",
    "Office": "none",
    "OneNote": "mac",
    "Outlook": "mac",
    "Photoshop": "mac",
    "PowerPoint": "mac",
    "Premiere Pro": "both",
    "Premiere Rush": "mac",
    "Revit": "none",
    "SimpleWall": "win",
    "SketchUp": "none",
    "SketchUp Pro": "mac",
    "SpectraLayers Pro": "mac",
    "Substance 3D": "mac",
    "Substance 3D Designer": "mac",
    "Substance 3D Painter": "mac",
    "Substance 3D Sampler": "mac",
    "Talon": "none",
    "Topaz Gigapixel Pro": "mac",
    "Topaz Photo Pro": "mac",
    "Topaz Video Pro": "mac",
    "VST Live Pro": "mac",
    "WaveLab Pro": "mac",
    "Word": "mac",
    "ZBrush": "mac",
}


def is_compatible(app: str, platform: str) -> bool:
    """True si la app estaba disponible en esa plataforma en el catálogo.
    Las apps desconocidas (agregadas después) se muestran por defecto.
    """
    value = _APP_PLATFORMS.get(app, "both")
    if value == "none":
        return False
    if platform == "mac":
        return value in ("mac", "both")
    return value in ("win", "both")