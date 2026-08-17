APP_SPECS = {
    # Adobe
    "Photoshop":         {"disk": "20 GB (+100 GB scratch)", "ram_min": 8,  "ram_rec": 16, "gpu": "1.5 GB VRAM"},
    "Illustrator":       {"disk": "2.5 GB",                  "ram_min": 8,  "ram_rec": 16, "gpu": "1 GB VRAM"},
    "Premiere Pro":      {"disk": "10 GB",                   "ram_min": 8,  "ram_rec": 32, "gpu": "4 GB VRAM"},
    "After Effects":     {"disk": "8 GB",                    "ram_min": 8,  "ram_rec": 32, "gpu": "4 GB VRAM"},
    "Acrobat Pro":       {"disk": "4.5 GB",                  "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Lightroom Classic": {"disk": "10 GB",                   "ram_min": 8,  "ram_rec": 16, "gpu": "2 GB VRAM"},
    "Audition":          {"disk": "8 GB",                    "ram_min": 8,  "ram_rec": 16, "gpu": "---"},
    "InDesign":          {"disk": "3.6 GB",                  "ram_min": 8,  "ram_rec": 16, "gpu": "1 GB VRAM"},
    "Animate":           {"disk": "3 GB",                    "ram_min": 8,  "ram_rec": 16, "gpu": "1 GB VRAM"},
    "Bridge":            {"disk": "2 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Media Encoder":     {"disk": "4 GB",                    "ram_min": 8,  "ram_rec": 16, "gpu": "1 GB VRAM"},
    "Character Animator":{"disk": "5 GB",                    "ram_min": 8,  "ram_rec": 16, "gpu": "2 GB VRAM"},
    "Dreamweaver":       {"disk": "2 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Dimension":         {"disk": "5 GB",                    "ram_min": 8,  "ram_rec": 16, "gpu": "2 GB VRAM"},
    "InCopy":            {"disk": "1.5 GB",                  "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Substance 3D":      {"disk": "6 GB",                    "ram_min": 8,  "ram_rec": 32, "gpu": "4 GB VRAM"},
    # Otras apps (estimaciones — actualizar con specs oficiales)
    "CorelDRAW":         {"disk": "4 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "1 GB VRAM"},
    "DaVinci Resolve":   {"disk": "12 GB",                   "ram_min": 16, "ram_rec": 32, "gpu": "4 GB VRAM"},
    "FL Studio":         {"disk": "4 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Ableton Live":      {"disk": "6 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "AutoCAD":           {"disk": "12 GB",                   "ram_min": 8,  "ram_rec": 16, "gpu": "2 GB VRAM"},
    "Revit":             {"disk": "25 GB",                   "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "SketchUp":          {"disk": "2 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "1 GB VRAM"},
    "Office":            {"disk": "4 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Word":              {"disk": "2 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Excel":             {"disk": "2 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "PowerPoint":        {"disk": "2 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Outlook":           {"disk": "2 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "OneNote":           {"disk": "1 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Microsoft AutoUpdate (MAU)":              {"disk": "200 MB",                "ram_min": 1,  "ram_rec": 1,  "gpu": "---"},
    "Microsoft Office LTSC 2024 VL Serializer": {"disk": "10 MB",                 "ram_min": 1,  "ram_rec": 1,  "gpu": "---"},
    # Herramientas de optimización
    "Mole + Talon":      {"disk": "1 GB",                    "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Mole":              {"disk": "500 MB",                  "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "Talon":             {"disk": "500 MB",                  "ram_min": 2,  "ram_rec": 4,  "gpu": "---"},
    "SimpleWall":        {"disk": "50 MB",                   "ram_min": 1,  "ram_rec": 2,  "gpu": "---"},
    "Blender": {"disk": "5 GB", "ram_min": 8, "ram_rec": 16, "gpu": "2 GB VRAM"},
    # Adobe XD + Substance 3D (individuales)
    "Adobe XD":          {"disk": "2 GB",                    "ram_min": 4,  "ram_rec": 8,  "gpu": "1 GB VRAM"},
    "Substance 3D Designer":  {"disk": "8 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Substance 3D Painter":   {"disk": "8 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Substance 3D Sampler":   {"disk": "6 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    # Apple (requieren macOS 15.6+)
    "Apple Creator Studio":   {"disk": "10 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Apple Final Cut Pro":    {"disk": "8 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Apple Final Cut Pro CS": {"disk": "8 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Apple Pro Bundle":       {"disk": "20 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    "Logic Pro":              {"disk": "6 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Logic Pro CS":           {"disk": "6 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Premiere Rush":          {"disk": "4 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "2 GB VRAM"},
    "FxFactory":              {"disk": "2 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "2 GB VRAM"},
    "Fusion Studio":          {"disk": "10 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    # Arquitectura
    "Archicad":               {"disk": "25 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "2 GB VRAM"},
    "SketchUp Pro":           {"disk": "4 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "2 GB VRAM"},
    "ZBrush":                 {"disk": "6 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},
    # Steinberg
    "Cubase Pro":             {"disk": "15 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "---"},
    "Dorico Pro":             {"disk": "5 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "Nuendo":                 {"disk": "15 GB",              "ram_min": 8,  "ram_rec": 16, "gpu": "---"},
    "GrooveAgent":            {"disk": "10 GB",              "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "SpectraLayers Pro":      {"disk": "6 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "VST Live Pro":           {"disk": "6 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    "WaveLab Pro":            {"disk": "10 GB",              "ram_min": 4,  "ram_rec": 8,  "gpu": "---"},
    # Topaz
    "Topaz Gigapixel Pro":    {"disk": "2 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "2 GB VRAM"},
    "Topaz Photo Pro":        {"disk": "3 GB",               "ram_min": 4,  "ram_rec": 8,  "gpu": "2 GB VRAM"},
    "Topaz Video Pro":        {"disk": "4 GB",               "ram_min": 8,  "ram_rec": 16, "gpu": "4 GB VRAM"},

}
INSTALL_INSTRUCTIONS = {
    "DaVinci Resolve": [
        "Open the image DaVinci_Resolve_Studio_21.0.3_Mac.dmg",
        "Launch the installer Install Resolve 21.0.3",
        "Perform a standard installation.",
        "Simply click the buttons: Continue, Install, and Close.",
        "The installation process will require your Mac password (the same one you use to log in).",
        "Perform a similar installation for file DaVinci Lic.pkg",
        "Last Install VL.pkg",
        "Done, enjoy!",
    ],
}
# Cada programa puede tener un método de descarga diferente.
# Por ahora, solo Adobe tiene métodos configurados (torrent/GenP).
# Los demás programas se instalarán manualmente por el proveedor.
#
# Métodos disponibles:
#   "torrent"  → Torrent (magnet link en TORRENT_MAGNETS)
#                Se muestra como: Aplicación preparchada
#   "GenP"     → Parche GenP para activar (HTTP, solo si ya tienen Adobe)
#   "http"     → Descarga directa por HTTP (futuro)
#   "torrent"  → Torrent genérico (futuro)
#   None       → Sin descarga automática (instalación manual por proveedor)

DOWNLOAD_METHODS = {
    # Adobe — métodos configurados
    "Photoshop":         "torrent",
    "Illustrator":       "torrent",
    "Premiere Pro":      "torrent",
    "After Effects":     "torrent",
    "Lightroom Classic": "torrent",
    "Acrobat Pro":       "torrent",
    "Audition":          "torrent",
    "InDesign":          "torrent",
    "Animate":           "torrent",
    "Bridge":            "torrent",
    "Media Encoder":     "torrent",
    "Character Animator":"torrent",
    "Dreamweaver":       "torrent",
    "Dimension":         "torrent",
    "InCopy":            "torrent",
    "Substance 3D":      "torrent",
    "Substance 3D Designer": "torrent",
    "Substance 3D Painter":  "torrent",
    "Substance 3D Sampler":  "torrent",
    "Adobe XD":          "torrent",
    # Herramientas de optimización
    "Mole + Talon":      "combo",
    "Mole":              "http",
    "Talon":             None,  # sin link válido (404 en GitHub): instalación manual
    "SimpleWall":        "http",
    # Otras apps — sin descarga automática (instalación manual por proveedor)
    "CorelDRAW":         "http",
    "DaVinci Resolve":   "http",
    "FL Studio":         "http",
    "Ableton Live":      "http",
    "AutoCAD":           "http",
    "Revit":             None,
    "SketchUp":          None,
    "Archicad":          "http",
    "SketchUp Pro":      "http",
    "Fusion Studio":     "http",
    "FxFactory":         "http",
    "ZBrush":            "http",
    "Topaz Gigapixel Pro": "http",
    "Topaz Photo Pro":   "http",
    "Topaz Video Pro":   "http",
    "Premiere Rush":     "http",
    "Apple Creator Studio": "http",
    "Apple Final Cut Pro": "http",
    "Apple Final Cut Pro CS": "http",
    "Apple Pro Bundle":  "http",
    "Logic Pro":         "http",
    "Logic Pro CS":      "http",
    "Cubase Pro":        "http",
    "Dorico Pro":        "http",
    "GrooveAgent":       "http",
    "Nuendo":            "http",
    "SpectraLayers Pro": "http",
    "VST Live Pro":      "http",
    "WaveLab Pro":       "http",
    # Office: el padre se resuelve en sub-apps + componentes core.
    # Cada sub-app se descarga de forma directa con su propio link.
    "Office":            "group",
    "Word":              "http",
    "Excel":             "http",
    "PowerPoint":        "http",
    "Outlook":           "http",
    "OneNote":           "http",
    "Microsoft AutoUpdate (MAU)": "http",
    "Microsoft Office LTSC 2024 VL Serializer": "http",

    "Blender": "http",
}
INSTALL_QUESTIONS = {
    "adobe_oficiales": {
        "apps": [
            "Photoshop", "Illustrator", "Premiere Pro", "After Effects",
            "Lightroom Classic", "Acrobat Pro", "Audition", "InDesign",
            "Animate", "Bridge", "Media Encoder", "Character Animator",
            "Dreamweaver", "Dimension", "InCopy", "Substance 3D",
        ],
        "question": "¿TIENES PROGRAMAS\nADOBE OFICIALES\nINSTALADOS?",
        "options": {
            "si":    {"method": "GenP"},
            "no":    {"method": "torrent"},
        }
    },
    # ── DORMIDO: activar cuando la app tenga opción de parche ──
    # "davinci_studio": {
    #     "apps": ["DaVinci Resolve"],
    #     "question": "¿Ya tienes DaVinci Studio instalado?",
    #     "options": {
    #         "si": {"method": "ya_instalado"},
    #         "no": {"method": "davinci_installer"},
    #     }
    # },
}
