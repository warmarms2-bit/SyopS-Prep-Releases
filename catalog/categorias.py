# ── REGISTRO DE CATEGORÍAS Y APPS ────────────────────────────────────
# CATEGORY_META: metadata de presentación por categoría (descripción, fondo).
# APP_CATEGORY: registry app → categoría (única fuente de verdad de membresía).
# SOFTWARE_CATEGORIES se genera automáticamente desde estos dos dicts.

CATEGORY_META = {
    "graphic_design": {
        "label_key": "catalog.categories.graphic_design.name",
        "description_key": "catalog.categories.graphic_design.description",
        "bg": "assets/images/syops_bg_2.jpg",
    },
    "video_film": {
        "label_key": "catalog.categories.video_film.name",
        "description_key": "catalog.categories.video_film.description",
        "bg": "assets/images/syops_bg_3.jpg",
    },
    "audio_music": {
        "label_key": "catalog.categories.audio_music.name",
        "description_key": "catalog.categories.audio_music.description",
        "bg": "assets/images/syops_bg_4.jpg",
    },
    "architecture": {
        "label_key": "catalog.categories.architecture.name",
        "description_key": "catalog.categories.architecture.description",
        "bg": "assets/images/syops_bg_5.jpg",
    },
    "office": {
        "label_key": "catalog.categories.office.name",
        "description_key": "catalog.categories.office.description",
        "bg": "assets/images/syops_bg_2.jpg",
    },
    "optimization": {
        "label_key": "catalog.categories.optimization.name",
        "description_key": "catalog.categories.optimization.description",
        "bg": "assets/images/syops_bg_2.jpg",
    },
    "utilities": {
        "label_key": "catalog.categories.utilities.name",
        "description_key": "catalog.categories.utilities.description",
        "bg": "assets/images/syops_bg_2.jpg",
    },
}

APP_CATEGORY = {
    "Photoshop": "graphic_design",
    "Illustrator": "graphic_design",
    "InDesign": "graphic_design",
    "CorelDRAW": "graphic_design",
    "Acrobat Pro": "graphic_design",
    "Dimension": "graphic_design",
    "Substance 3D": "graphic_design",
    "Substance 3D Designer": "graphic_design",
    "Substance 3D Painter": "graphic_design",
    "Substance 3D Sampler": "graphic_design",
    "ZBrush": "graphic_design",
    "Topaz Gigapixel Pro": "graphic_design",
    "Topaz Photo Pro": "graphic_design",
    "Adobe XD": "graphic_design",
    "Lightroom Classic": "graphic_design",
    "InCopy": "graphic_design",
    "Dreamweaver": "graphic_design",
    "Premiere Pro": "video_film",
    "After Effects": "video_film",
    "Animate": "video_film",
    "Character Animator": "video_film",
    "DaVinci Resolve": "video_film",
    "Media Encoder": "video_film",
    "Bridge": "video_film",
    "Premiere Rush": "video_film",
    "Apple Creator Studio": "video_film",
    "Apple Final Cut Pro": "video_film",
    "Apple Final Cut Pro CS": "video_film",
    "Apple Pro Bundle": "video_film",
    "Fusion Studio": "video_film",
    "FxFactory": "video_film",
    "Topaz Video Pro": "video_film",
    "Audition": "audio_music",
    "FL Studio": "audio_music",
    "Ableton Live": "audio_music",
    "Logic Pro": "audio_music",
    "Logic Pro CS": "audio_music",
    "Cubase Pro": "audio_music",
    "Dorico Pro": "audio_music",
    "GrooveAgent": "audio_music",
    "Nuendo": "audio_music",
    "SpectraLayers Pro": "audio_music",
    "VST Live Pro": "audio_music",
    "WaveLab Pro": "audio_music",
    "AutoCAD": "architecture",
    "Revit": "architecture",
    "SketchUp": "architecture",
    "Archicad": "architecture",
    "SketchUp Pro": "architecture",
    "Office": "office",
    "Mole + Talon": "optimization",
    "SimpleWall": "utilities",

    "Blender": "graphic_design",
}


def _build_software_categories(meta: dict, app_cat: dict) -> dict:
    """Genera SOFTWARE_CATEGORIES desde CATEGORY_META + APP_CATEGORY.

    Agrupa apps por categoría (orden de primera aparición en app_cat),
    adjunta metadata de presentación, y agrega "Ver todo" al final.
    """
    # Agrupar apps por categoría (respetando orden de primera aparición)
    grouped = {}
    for app, cat in app_cat.items():
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(app)

    # Construir dict final en orden de meta.keys()
    result = {}
    for cat_name in meta.keys():
        meta_data = meta[cat_name]
        result[cat_name] = {
            "label_key": meta_data["label_key"],
            "description_key": meta_data["description_key"],
            "bg": meta_data["bg"],
            "apps": grouped.get(cat_name, []),
        }

    # "Ver todo" = todas las apps únicas en orden de primera aparición
    all_apps = []
    for apps_list in grouped.values():
        for app in apps_list:
            if app not in all_apps:
                all_apps.append(app)
    result["all"] = {
        "label_key": "catalog.categories.all.name",
        "description_key": "catalog.categories.all.description",
        "bg": "assets/images/syops_bg_2.jpg",
        "apps": all_apps,
    }

    return result


SOFTWARE_CATEGORIES = _build_software_categories(CATEGORY_META, APP_CATEGORY)
OFFICE_PARENT = "Office"
OFFICE_APPS = frozenset([
    "Word", "Excel", "PowerPoint", "Outlook", "OneNote",
])
OFFICE_CORE_APPS = [
    "Microsoft AutoUpdate (MAU)",
    "Microsoft Office LTSC 2024 VL Serializer",
]


def _expand_office_for_downloads(apps, office_sub_apps=None):
    """Reemplaza 'Office' por las sub-apps elegidas + componentes core.
    Cada sub-app se descarga de forma directa con su propio link."""
    result = []
    has_office = False
    for a in apps:
        if a == OFFICE_PARENT:
            has_office = True
            if office_sub_apps:
                result.extend(office_sub_apps)
        else:
            result.append(a)
    if has_office:
        result.extend(OFFICE_CORE_APPS)
    return result


def _expand_office_for_display(apps, office_sub_apps=None):
    """Expande 'Office' a un texto descriptivo para proformas/resumen."""
    result = []
    for a in apps:
        if a == OFFICE_PARENT:
            subs = office_sub_apps or []
            if subs:
                result.append(f"Office ({', '.join(subs)})")
            else:
                result.append("Office")
        else:
            result.append(a)
    return result
