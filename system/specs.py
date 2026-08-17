from catalog.data import APP_SPECS, TOOL_DESCS, _expand_apps
from i18n import _

def get_specs_summary(apps: list) -> str:
    apps = _expand_apps(apps)
    if not apps:
        return _("seleccion.selecciona_programas")
    if apps == ["GenP"]:
        return _("seleccion.metodo_genp")
    # Tools muestran descripción en lugar de requisitos
    tool_only = all(a in TOOL_DESCS for a in apps)
    if tool_only:
        lines = []
        for app in apps:
            lines.append(f"{app}")
            lines.append(f"{TOOL_DESCS.get(app, '')}")
            lines.append("")
        return "\n".join(lines)
    lines = []
    for app in apps:
        s = APP_SPECS.get(app, {})
        if not s:
            continue
        desc = TOOL_DESCS.get(app, "")
        if desc:
            lines.append(f"{app}")
            lines.append(f"  {desc}")
            lines.append("")
        else:
            lines.append(f"{app}")
            lines.append(_("seleccion.specs_disco", disk=s.get("disk", "N/A")))
            lines.append(_("seleccion.specs_ram", ram_min=s.get("ram_min", 0), ram_rec=s.get("ram_rec", 0)))
            lines.append(_("seleccion.specs_gpu", gpu=s.get("gpu", "---")))
            lines.append("")
    if not lines:
        return _("seleccion.sin_requisitos")
    return "\n".join(lines)
def _format_specs_line(specs: dict, indent: str = "") -> str:
    """Formats a single app's specs from the locale catalog."""
    return indent + _(
        "resumen.specs_line",
        disk=specs.get("disk", "N/A"),
        ram_min=specs.get("ram_min", 0),
        ram_rec=specs.get("ram_rec", 0),
        gpu=specs.get("gpu", "---"),
    )
def _accumulate_specs(apps: list) -> tuple:
    total_disk = 0.0
    max_ram_min = 0
    max_ram_rec = 0
    for app in apps:
        s = APP_SPECS.get(app, {})
        if not s:
            continue
        try:
            parts = s.get("disk", "0").split()
            value = float(parts[0])
            unit = parts[1].upper() if len(parts) > 1 else "GB"
            if unit == "MB":
                value /= 1024
            total_disk += value
        except (ValueError, IndexError):
            pass
        max_ram_min = max(max_ram_min, s.get("ram_min", 0))
        max_ram_rec = max(max_ram_rec, s.get("ram_rec", 0))
    return total_disk, max_ram_min, max_ram_rec
def _compatibility_lines(system_info: dict, apps: list) -> list[str]:
    """Builds all customer-facing compatibility copy through locale keys."""
    total_disk, max_ram_min, max_ram_rec = _accumulate_specs(apps)
    sys_ram = system_info.get("ram", 0)
    sys_disk_free = system_info.get("disk", {}).get("free", 0)
    lines = ["\n" + _("resumen.compatibilidad")]
    if sys_ram >= max_ram_rec:
        lines.append(_("resumen.compat_ram_recomendada", ram=sys_ram, recomendada=max_ram_rec))
    elif sys_ram >= max_ram_min:
        lines.append(_("resumen.compat_ram_minima", ram=sys_ram, minima=max_ram_min, recomendada=max_ram_rec))
    else:
        lines.append(_("resumen.compat_ram_insuficiente", ram=sys_ram, minima=max_ram_min))
    ram_disk_key = "resumen.compat_disco_ok" if sys_disk_free >= total_disk else "resumen.compat_disco_insuficiente"
    lines.append(_(ram_disk_key, disco=sys_disk_free, necesario=total_disk))
    return lines