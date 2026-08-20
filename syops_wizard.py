#!/usr/bin/env python3
"""SyopS Prep — Wizard interactivo en terminal.

Replica el flujo del asistente de la UI (la MISMA lógica, sin ventanas):

    Inicio → Diagnóstico → Categoría → Selección (+ preguntas)
    → Activación (código) → Resumen → Descarga → Final

Usa solo el dominio puro (catalog/services/system/app_config); el estado
de activación y las descargas se comparten con la UI (SYOPS_DIR).

Ejecutar:
    python3 syops_wizard.py
"""

import asyncio
import os
import re
import sys
from pathlib import Path

# En Windows la consola no pinta ANSI por defecto (sale `←[36m` como texto).
# Esto activa el soporte VT de la consola (Win10+); si no se puede (consola
# vieja o salida redirigida a pipe), se desactivan los colores y se imprime
# texto limpio.
def _setup_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        os.system("")
        return True
    except Exception:
        return False


_COLOR_OK = _setup_color()

from app_config import (
    APP_VERSION, SYOPS_DIR, DEFAULT_APPS, MAX_APPS, WHATSAPP_DISPLAY,
    LINK_SERVER_URL,
)
from catalog.base import IS_MAC, IS_WIN
from catalog.data import (
    SOFTWARE_CATEGORIES, ADOBE_APPS, OFFICE_PARENT, APP_SPECS, TOOL_DESCS,
)
from catalog.categorias import OFFICE_APPS, _expand_office_for_display
from catalog.specs import INSTALL_QUESTIONS, INSTALL_INSTRUCTIONS
from system.specs import _format_specs_line, _compatibility_lines
from catalog.adobe import ADOBE_METHODS
from catalog.adobe_helpers import _adobe_tools_for_method
from services.seleccion_logic import build_download_apps
from services.download_engine import DownloadEngine
from services.download_manager import DownloadManager
from services.download_resolvers import _write_instructions_file
from system.hardware import get_hwid, get_machine_id, get_system_scan_info
from i18n import _

# ── Colores ANSI (consola) ─────────────────────────────────────────
_B = "\033[1m"; _D = "\033[2m"
_CY = "\033[33m"; _GR = "\033[32m"; _YE = "\033[33m"; _RD = "\033[31m"
_R = "\033[0m"


def _c(text, color):
    if not _COLOR_OK:
        return re.sub(r"\x1b\[[0-9;]*m", "", text) if text else text
    return f"{color}{text}{_R}"


def _sep(char="═", color=_CY):
    print(_c(char * 64, color))


class WizardCancelled(Exception):
    """El usuario canceló el proceso (tecla 'q' o sinónimos)."""


def _readline():
    """Lee una línea del teclado.

    Casos:
    • stdin es la terminal (lo normal)         → lee de stdin.
    • one-liner `curl | bash` en macOS/linux   → stdin quedó como tubería
      cerrada (EOF); se reabre la terminal real (/dev/tty) para poder leer
      Enter y el teclado.
    • stdin no es terminal ni tubería (/dev/null, archivo, lanzado en
      segundo plano)                           → se lee stdin: llega EOF y
      _ask cierra el wizard limpio (no se cuelga esperando /dev/tty).
    En Windows el one-liner corre en la misma consola, así que stdin sirve.
    """
    try:
        if sys.stdin.isatty():
            line = sys.stdin.readline()
        elif sys.platform != "win32" and _stdin_is_pipe():
            with open("/dev/tty", "r") as tty:
                line = tty.readline()
        else:
            line = sys.stdin.readline()
    except OSError:
        line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line


def _stdin_is_pipe():
    try:
        import stat
        return stat.S_ISFIFO(os.fstat(0).st_mode)
    except OSError:
        return False


def _ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    try:
        print(f"{_c('» ', _GR)}{prompt}{suffix}: ", end="", flush=True)
        raw = _readline().strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)
    if raw.lower() in ("q", "salir", "exit", "quit"):
        raise WizardCancelled()
    return raw or (default or "")


def _yes_no(prompt, default="s"):
    while True:
        r = _ask(f"{prompt} (s/n)", default=default).lower()
        if r in ("s", "si", "sí", "y", "yes"):
            return True
        if r in ("n", "no"):
            return False
        print(_c("  ↳ Respondé 's' o 'n'.", _YE))


def _parse_numbers(raw: str, max_n: int):
    """Parsea la entrada del usuario en una lista de números válidos.

    Acepta comas, espacios o rangos, en cualquier combinación:
      "1,2,3"   "1 2 3"   "1, 2, 3"   "1-3"   "1 3-5"
    """
    nums = []
    for part in re.split(r"[\s,;]+", raw.strip()):
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                a, b = int(a), int(b)
            except ValueError:
                return None
            if a < 1 or b > max_n or a > b:
                return None
            nums.extend(range(a, b + 1))
        else:
            try:
                n = int(part)
            except ValueError:
                return None
            if n < 1 or n > max_n:
                return None
            nums.append(n)
    return nums


def _pick_numbers(max_n, limit=None, prompt="Elegí (ej: 1,3,5 o 1-3)"):
    while True:
        raw = _ask(prompt)
        nums = _parse_numbers(raw, max_n)
        if nums is None:
            print(_c(f"  ↳ Números entre 1 y {max_n}, separados por coma/espacio "
                     f"(ej: 1,3,5 o 1-3).", _YE))
            continue
        if not nums:
            print(_c("  ↳ Elegí al menos uno.", _YE))
            continue
        if limit is not None and len(nums) > limit:
            print(_c(f"  ↳ Máximo {limit} programas en tu plan.", _YE))
            continue
        return nums


def _list_apps(apps, already=None):
    already = already or []
    for i, app in enumerate(apps, 1):
        method = _method_label(app)
        mark = _c(" ✓ ya elegido", _GR) if app in already else ""
        print(f"  {_c(str(i).rjust(2), _CY)}. {app:<28} {_c(method, _D)}{mark}")


def _method_label(app):
    from catalog.data import DOWNLOAD_METHODS
    if app in ADOBE_APPS:
        return "Adobe (método a elegir)"
    m = DOWNLOAD_METHODS.get(app)
    return m or "manual"


_OS_NAME = "macOS" if IS_MAC else ("Windows" if IS_WIN else "Linux")


def _html_to_text(text: str) -> str:
    """Quita etiquetas HTML simples (los textos i18n usan <b>...</b>)."""
    return re.sub(r"</?[a-zA-Z][^>]*>", "", text or "")


def _wrap_lines(text: str, indent: str = "", bullet: str = "") -> list[str]:
    """Envuelve el texto al ancho de la terminal respetando la sangría.

    La primera línea usa `indent + bullet`; las líneas de continuación se
    alinean bajo la primera letra del contenido (bullet o indent puro).
    """
    import shutil
    import textwrap
    cols = max(40, shutil.get_terminal_size((80, 20)).columns)
    lead = indent + (bullet + " " if bullet else "")
    sub = indent + (" " * (len(bullet) + 1) if bullet else "")
    width = max(30, cols - len(lead))
    return textwrap.fill(text, width=width,
                         initial_indent=lead, subsequent_indent=sub).split("\n")


def _code_type_for(max_apps: int) -> str:
    """Tipo de licencia según max_apps (sin backend): 99 = Full Pack."""
    return "adobe_full_pack" if int(max_apps or 0) >= 99 else "standard"


def _platform_apps(apps):
    """Delega en el esqueleto (app_flow) — la regla vive en app_flow."""
    from app_flow import platform_apps as _fa
    return _fa(apps, IS_MAC, IS_WIN)


def _pick_adobe_method(adobe_apps):
    """Delega en el esqueleto (app_flow) — la regla vive en app_flow."""
    from app_flow import preseleccionar_metodo
    compatible, default = preseleccionar_metodo(adobe_apps)
    return compatible, default


class Wizard:
    """Vista de terminal sobre el esqueleto app_flow (FlujoMotor).

    El estado y las reglas viven en self.motor; este wizard solo se ocupa
    de la presentación (input/output). Las propiedades delegadas mantienen
    compatibilidad con los tests y con el código existente.
    """

    def __init__(self):
        from app_flow import FlujoMotor
        self.client_id = get_machine_id()
        self.hwid = get_hwid()
        self.motor = FlujoMotor(self.client_id, self.hwid, IS_MAC, IS_WIN)

    def _link_provider(self):
        """Proveedor de links (Tier 1.5) si hay un Google Apps Script configurado.

        Lee `SYOPS_LINK_SERVER` (env, la URL /exec del Apps Script) y usa el
        código de activación guardado. Si no hay URL, devuelve None → el
        wizard resuelve localmente (Tier 1). El cliente no trae el catálogo;
        pide cada link al script, que valida la activación en Google Sheets.
        """
        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            return None
        try:
            from services.activation import load_activation_state
            _cid, code, _max, _hid, _used, _type, _created = load_activation_state(SYOPS_DIR)
        except Exception:
            code = ""
        from services.google_link_provider import GoogleLinkProvider
        return GoogleLinkProvider(server, self.client_id, self.hwid, code or "")

    # ── Estado delegado al motor (app_flow) ────────────────────────
    @property
    def cat(self):
        return self.motor.state.categoria

    @cat.setter
    def cat(self, value):
        self.motor.elegir_categoria(value)

    @property
    def selected_apps(self):
        return self.motor.state.seleccion

    @selected_apps.setter
    def selected_apps(self, value):
        self.motor.set_seleccion(value)

    @property
    def office_sub_apps(self):
        return self.motor.state.office_sub

    @office_sub_apps.setter
    def office_sub_apps(self, value):
        self.motor.elegir_office(value)

    @property
    def adobe_patched(self):
        return self.motor.state.adobe_patched

    @adobe_patched.setter
    def adobe_patched(self, value):
        self.motor.marcar_adobe_patched(value)

    @property
    def adobe_method(self):
        return self.motor.state.adobe_method

    @adobe_method.setter
    def adobe_method(self, value):
        self.motor.elegir_metodo_adobe(value)

    @property
    def max_apps(self):
        return self.motor.state.max_apps

    @max_apps.setter
    def max_apps(self, value):
        self.motor.set_limite(value)

    @property
    def activation_status(self):
        return self.motor.state.activado

    @activation_status.setter
    def activation_status(self, value):
        self.motor.set_activacion(bool(value), self.max_apps, self.activation_type)

    @property
    def activation_type(self):
        return self.motor.state.tipo

    @activation_type.setter
    def activation_type(self, value):
        self.motor.set_activacion(self.activation_status, self.max_apps, value)

    # ── Paso 0: estado de activación (solo lectura) ────────────────
    def load_activation(self):
        """Carga el estado guardado sin pedir nada. La activación se
        solicita DESPUÉS del resumen (misma lógica que la UI)."""
        try:
            from services.activation import (
                get_activated_max_apps, get_activation_type, is_activated,
            )
            if is_activated(SYOPS_DIR, self.client_id, self.hwid):
                self.activation_status = True
                self.max_apps = get_activated_max_apps(SYOPS_DIR, self.client_id, self.hwid) or DEFAULT_APPS
                self.activation_type = get_activation_type(SYOPS_DIR, self.client_id, self.hwid)
        except RuntimeError:
            # Sin secret de activación (o backend ausente): se continúa sin
            # activación; el cliente verá el mensaje amigable al pedir el código.
            self.activation_status = False

    # ── Activación solicitada tras el resumen ──────────────────────
    def check_activation(self):
        from services.activation import (
            get_activated_max_apps, get_activation_type, is_activated,
        )
        ok = is_activated(SYOPS_DIR, self.client_id, self.hwid)
        if ok:
            self.activation_status = True
            self.max_apps = get_activated_max_apps(SYOPS_DIR, self.client_id, self.hwid) or DEFAULT_APPS
            self.activation_type = get_activation_type(SYOPS_DIR, self.client_id, self.hwid)
            return
        self._ask_activation_code()

    # ── Paso 1: inicio ─────────────────────────────────────────────
    def show_inicio(self):
        _sep()
        from app_banner import BANNER
        print(_c(_B + "   " + BANNER.replace("\n", "\n   "), _CY))
        print(_c(_B + "   SyopS", _CY) + _c(f"  v{APP_VERSION}", _D))
        print(_c("   Asistente de descarga de software (terminal)", _D))
        _sep()
        print("  Este asistente te guía igual que la aplicación:")
        print("  1. Diagnóstico del sistema")
        print("  2. Elegir categoría y programas")
        print("  3. Responder las preguntas")
        print("  4. Descargar los archivos")
        print()
        _ask("Presioná Enter para comenzar", default="")
        print()

    # ── Paso 2: diagnóstico ────────────────────────────────────────
    def show_scan(self):
        _sep()
        print(_c(_B + "  DIAGNÓSTICO DEL SISTEMA", _CY))
        _sep()
        scan = get_system_scan_info()
        disk = scan.get("disk", {})
        free_gb = disk.get("free_gb") or disk.get("free")
        print(f"  CPU        : {scan.get('cpu')}")
        print(f"  RAM        : {scan.get('ram')} GB")
        print(f"  Disco libre: {free_gb} GB")
        print(f"  OS         : {scan.get('os')}")
        print(f"  Hostname   : {scan.get('hostname')}")
        print()
        print(_c(f"  ✓ Sistema detectado: {_OS_NAME}.", _GR))
        if IS_MAC:
            print(_c("  Solo se mostrarán programas disponibles para macOS.", _D))
        elif IS_WIN:
            print(_c("  Solo se mostrarán programas disponibles para Windows.", _D))
        print()
        _ask("Presioná Enter para continuar", default="")
        print()

    # ── Paso 3: categoría ──────────────────────────────────────────
    def choose_category(self):
        cats = [(k, v) for k, v in SOFTWARE_CATEGORIES.items() if k != "all"]
        _sep()
        print(_c(_B + "  ELEGÍ UNA CATEGORÍA", _CY))
        _sep()
        for i, (key, info) in enumerate(cats, 1):
            label = _(info.get("label_key", key))
            from app_flow.flujo import platform_apps
            n = len(platform_apps(info.get("apps", []), IS_MAC, IS_WIN))
            print(f"  {_c(str(i).rjust(2), _CY)}. {label:<30} {_c(f'({n} programas)', _D)}")
        while True:
            r = _ask("Categoría")
            try:
                idx = int(r)
                if 1 <= idx <= len(cats):
                    break
            except ValueError:
                pass
            print(_c(f"  ↳ Elegí un número entre 1 y {len(cats)}.", _YE))
        self.cat = cats[idx - 1][0]
        print()

    # ── Paso 4: selección + preguntas ──────────────────────────────
    def ask_adobe_question(self):
        """Pregunta de INSTALL_QUESTIONS si la categoría tiene Adobe.

        SOLO aplica en Windows (GenP patch). En macOS se va directo a
        elegir el método de instalación (AIO, Activation Tool), como la UI.
        """
        if not self.motor.pregunta_adobe_pendiente():
            return
        adobe_selected = self.motor.adobe_seleccionados
        q = INSTALL_QUESTIONS.get("adobe_oficiales")
        if not q:
            return
        _sep()
        print(_c(_B + "  PREGUNTA", _CY))
        _sep()
        for line in q["question"].split("\n"):
            print(f"  {line}")
        print()
        yes = _yes_no("¿Tenés programas Adobe oficiales instalados?", default="n")
        if not yes:
            print(_c("  ↳ Perfecto: las apps de Adobe se descargarán (torrent).", _D))
            return
        _sep()
        print(_c(_B + "  MARCÁ LOS ADOBE QUE YA TENÉS INSTALADOS", _CY))
        print(_c("  (se patchearán con GenP, no se descargan)", _D))
        _sep()
        _list_apps(adobe_selected)
        nums = _pick_numbers(len(adobe_selected), prompt="¿Cuáles ya tenés? (0 = ninguno)")
        self.motor.marcar_adobe_patched([adobe_selected[i - 1] for i in nums])
        print(_c(f"  ↳ Patcheados con GenP: {', '.join(self.adobe_patched) or 'ninguno'}", _D))
        print()

    def choose_apps(self):
        """Elige apps de la categoría actual ACUMULANDO sobre la selección
        previa (multi-categoría), respetando el límite del plan."""
        while True:
            all_apps = list(SOFTWARE_CATEGORIES[self.cat]["apps"])
            # Solo apps con link para el SO actual (regla del esqueleto).
            apps = self.motor.apps_actuales or []
            if not all_apps:
                apps = []
            hidden = self.motor.ocultas or [a for a in all_apps if a not in apps]
            if not apps:
                print(_c(f"  ↳ Ningún programa de esa categoría está disponible "
                         f"en {_OS_NAME} (solo: {', '.join(hidden)}).", _YE))
                print(_c("  Elegí otra categoría.", _YE))
                self.choose_category()
                continue
            break

        if not self.motor.puede_agregar():
            print(_c(f"  Ya elegiste {self.max_apps} apps (máximo de tu plan).", _YE))
            return

        _sep()
        print(_c(_B + "  SELECCIÓN DE PROGRAMAS", _CY))
        print(_c(f"  Elegidos: {len(self.selected_apps)}/{self.max_apps} | "
                 f"plataforma: {_OS_NAME} | categoría actual: "
                 f"{_(SOFTWARE_CATEGORIES[self.cat]['label_key'])}", _D))
        _sep()
        _list_apps(apps, already=self.selected_apps)
        if hidden:
            print(_c(f"  (ocultos por no estar disponibles en {_OS_NAME}: "
                     f"{', '.join(hidden)})", _D))
        print()
        remaining = max(0, self.max_apps - len(self.selected_apps))
        nums = _pick_numbers(len(apps), limit=remaining,
                             prompt="¿Qué programas querés? (números)")
        new_apps = [apps[i - 1] for i in nums]
        self.motor.agregar_apps(new_apps)
        print(_c(f"  ↳ Selección actual: {', '.join(self.selected_apps)}", _GR))
        print()

        # Requisitos mínimos de las apps recién elegidas (como specs_info).
        self._show_selected_specs(new_apps)

        # Office → sub-apps (misma página OFFICE de la UI)
        if OFFICE_PARENT in new_apps:
            self.choose_office()

    def choose_adobe_method_if_needed(self):
        """En macOS: elegir el método Adobe sobre el total seleccionado.
        En Windows las apps no parcheadas bajan por torrent (como la UI)."""
        if self.motor.necesita_metodo_adobe():
            self.choose_adobe_method(self.motor.adobe_a_descargar)

    def _show_selected_specs(self, apps=None):
        """Requisitos mínimos por app seleccionada (igual que specs_info)."""
        from catalog.data import APP_SPECS, TOOL_DESCS
        apps = apps or self.selected_apps
        lines = []
        for app in apps:
            desc = TOOL_DESCS.get(app)
            if desc:
                lines.append(f"  • {app}: {desc}")
                continue
            s = APP_SPECS.get(app)
            if not s:
                continue
            lines.append(f"  • {app}")
            lines.append(_format_specs_line(s, "      "))
        if lines:
            print(_c(_B + "  REQUISITOS MÍNIMOS", _CY))
            for ln in lines:
                print(_c(ln, _D))
            print()

    def choose_office(self):
        _sep()
        print(_c(_B + "  MICROSOFT OFFICE — ELEGÍ LAS APPS", _CY))
        _sep()
        office_list = sorted(OFFICE_APPS)  # orden estable (OFFICE_APPS es frozenset)
        _list_apps(office_list)
        print()
        nums = _pick_numbers(len(office_list), prompt="¿Qué apps de Office querés? (números)")
        self.office_sub_apps = [office_list[i - 1] for i in nums]
        print(_c(f"  ↳ Office: {', '.join(self.office_sub_apps)}", _D))
        print()

    def choose_adobe_method(self, adobe_apps):
        """Elige el método de Adobe en macOS (misma lógica que la UI):

        - SOLO se ofrecen métodos que cubren TODAS las apps elegidas y
          descargan apps (aio_macked, aio_sice, multilang_sice).
          activation_tool queda fuera (no descarga apps).
        - Preselección: aio_macked si es compatible; si no, el único/primero.
        """
        methods = [m for m in ADOBE_METHODS if m != "activation_tool"]
        compatible, default = _pick_adobe_method(adobe_apps)
        only_compatible = [m for m in methods if m in compatible]

        _sep()
        print(_c(_B + "  MÉTODO DE DESCARGA PARA ADOBE", _CY))
        print(_c(f"  Apps: {', '.join(adobe_apps)}", _D))
        _sep()
        if not only_compatible:
            # Sin método que cubra todas: mostrar todos con advertencia
            # (no se puede descargar la selección completa con uno solo).
            print(_c("  ⚠  Ningún método cubre TODAS las apps elegidas.", _RD))
            for i, m in enumerate(methods, 1):
                print(f"  {_c(str(i).rjust(2), _CY)}. {m:<18}")
                self._show_method_card(m, indent="     ", apps=adobe_apps)
        else:
            for i, m in enumerate(only_compatible, 1):
                info = ADOBE_METHODS[m]
                tag = "  ✓ recomendado" if info.get("recommended") else ""
                print(f"  {_c(str(i).rjust(2), _CY)}. {m:<18}{_c(tag, _GR)}")
                self._show_method_card(m, indent="     ", apps=adobe_apps)
        print()
        while True:
            r = _ask("Ingresá el número del método")
            try:
                idx = int(r)
                if 1 <= idx <= len(only_compatible):
                    self.adobe_method = only_compatible[idx - 1]
                    break
            except ValueError:
                pass
            if not r and default in only_compatible:
                self.adobe_method = default
                break
            if only_compatible:
                print(_c(f"  ↳ Elegí un número entre 1 y {len(only_compatible)}.", _YE))
            else:
                print(_c(f"  ↳ Elegí un número entre 1 y {len(methods)}.", _YE))
        print(_c(f"  ↳ Método Adobe: {self.adobe_method}", _D))
        print()

    def _clarify_app_mentions(self, text: str, apps) -> str:
        """Delega en el esqueleto (app_flow.clarify_mentions)."""
        from app_flow import clarify_mentions as _cm
        return _cm(text, apps)

    def _show_method_card(self, method: str, indent: str = "  ", apps=None):
        """Muestra descripción, bullets y warning del método (card de la UI)."""
        cfg = ADOBE_METHODS.get(method, {})
        desc = _(cfg.get("desc", ""))
        if not desc or desc.startswith("adobe."):
            return
        for ln in _wrap_lines(self._clarify_app_mentions(_html_to_text(desc), apps),
                              indent=indent):
            print(_c(ln, _D))
        for bkey in cfg.get("bullets", []):
            btxt = self._clarify_app_mentions(_html_to_text(_(bkey)), apps)
            if btxt and not btxt.startswith("adobe."):
                for ln in _wrap_lines(btxt, indent=indent, bullet="•"):
                    print(_c(ln, _D))
        # Versiones disponibles del método para las apps elegidas.
        if apps and method != "activation_tool":
            from catalog.adobe_helpers import _adobe_best_link
            vers = []
            for app in apps:
                _url, version = _adobe_best_link(method, app)
                if version:
                    vers.append(f"{app}: v{version}")
            if vers:
                texto = "Disponible en las versiones: " + "; ".join(vers)
                for ln in _wrap_lines(texto, indent=indent, bullet="⚠"):
                    print(_c(ln, _GR))

    # ── Paso 5: resumen + activación si falta ──────────────────────
    def show_resumen(self):
        _sep()
        print(_c(_B + "  RESUMEN DE LA SELECCIÓN", _CY))
        _sep()

        display = _expand_office_for_display(self.selected_apps, self.office_sub_apps)

        # 1) INFORMACIÓN DEL EQUIPO (igual que la UI)
        scan = get_system_scan_info()
        disk = scan.get("disk", {})
        print(_c(_B + "  " + _("resumen.info_equipo"), _D))
        print(_("resumen.info_equipo_linea", cpu=scan.get("cpu"), ram=scan.get("ram"),
                disco_libre=disk.get("free", 0), disco_total=disk.get("total", 0)))
        print()

        # 2) PROGRAMAS SELECCIONADOS + requisitos por app
        print(_c(_B + "  " + _("resumen.programas"), _D))
        for app in display:
            s = APP_SPECS.get(app)
            desc = TOOL_DESCS.get(app)
            if desc:
                print(f"  • {app}: {desc}")
            elif s:
                print(f"  • {app}")
                print(_c(_format_specs_line(s, "      "), _D))
            else:
                print(f"  • {app}")
        print()

        # 3) COMPATIBILIDAD con el equipo (igual que la UI)
        for ln in _compatibility_lines(scan, display):
            print(_c(ln, _GR if ("✓" in ln) else (_RD if "✗" in ln else _YE)))
        print()

        # 4) MÉTODO + apps + tools (igual que _update_method_label de la UI)
        self._show_method_sections()
        print()
        if not _yes_no("¿Confirmás la selección?", default="s"):
            print(_c("  Volvé a empezar la selección.", _YE))
            self.selected_apps = []
            return False
        self._send_selection(display)
        return True

    def _show_method_sections(self):
        """Método de descarga, apps Adobe con versión y tools (como la UI)."""
        from catalog.adobe_helpers import _adobe_best_link
        from catalog.tools import TOOL_APPS, _app_tools_for_app
        from services.seleccion_logic import describe_method

        app_methods = {}
        for a in self.selected_apps:
            if a == OFFICE_PARENT:
                continue
            if a in ADOBE_APPS:
                if a in self.adobe_patched:
                    app_methods[a] = "GenP"
                else:
                    app_methods[a] = self.adobe_method or "torrent"
            else:
                app_methods[a] = _method_label(a)
        if self.office_sub_apps:
            app_methods["Office"] = "http"

        sections = []
        tools = {app: m for app, m in app_methods.items() if app in TOOL_APPS}
        adobe_scope = ADOBE_APPS if self.adobe_method else frozenset()
        non_tools = {a: m for a, m in app_methods.items()
                     if a not in TOOL_APPS and a not in adobe_scope}

        if non_tools:
            unique = set(non_tools.values())
            if len(unique) == 1 and len(non_tools) > 1 and list(unique)[0] in ("http", None):
                sections.append(_("resumen.metodos_por_app"))
                for app, m in non_tools.items():
                    label = describe_method(app, m)
                    sections.append(_("resumen.metodo_por_app", app=app, metodo=label))
            elif len(unique) == 1:
                m = list(unique)[0]
                if m in ("http", None) and len(non_tools) == 1:
                    only = next(iter(non_tools))
                    sections.append(_("resumen.metodo_linea",
                                      metodo=describe_method(only, m)))
                else:
                    sections.append(_("resumen.metodo_linea", metodo=m))
            else:
                sections.append(_("resumen.metodos_por_app"))
                for app, m in non_tools.items():
                    label = m
                    if m in ("http", None):
                        label = describe_method(app, m)
                    sections.append(_("resumen.metodo_por_app", app=app, metodo=label))

        if self.adobe_method:
            label = _(ADOBE_METHODS.get(self.adobe_method, {}).get("label", self.adobe_method))
            sections.append(_("resumen.adobe_linea", metodo=label))
            adobe_apps = [a for a in app_methods if a in ADOBE_APPS
                          and a not in self.adobe_patched]
            if adobe_apps:
                for app in adobe_apps:
                    _url, version = _adobe_best_link(self.adobe_method, app)
                    label = f"  • {app}" if not version else f"  • {app} — {version}"
                    sections.append(label)
            # Solo las tools REALES del método elegido (Sentinel, Pop-Up
            # Blocker...). Los 'Patchers por app' (ADOBE_PATCHERS_SICE) NO
            # aplican a AIO: el patcher va incluido en el paquete.
            tool_names = [name for name, _ in _adobe_tools_for_method(self.adobe_method)]
            if tool_names:
                sections.append(_("resumen.tools_linea", tools=", ".join(tool_names)))

        if self.adobe_patched:
            sections.append(_("resumen.app_para_activar",
                              app=", ".join(self.adobe_patched)))

        if tools:
            sections.append(_("resumen.herramientas_seleccionadas"))
            for app, m in tools.items():
                sections.append(f"  • {app}")

        app_tools = {}
        for app in app_methods:
            # Las apps Adobe no llevan tools por app: si hay método, las
            # tools reales del método ya se listaron arriba; si no hay
            # método (Windows/GenP) se descargan frescas por torrent.
            if app in ADOBE_APPS:
                continue
            for tool in _app_tools_for_app(app):
                app_tools.setdefault(app, []).append(tool.get("name", tool))
        if app_tools:
            sections.append(_("resumen.tools_por_app_titulo"))
            for app in sorted(app_tools):
                sections.append(f"  • {app}: {', '.join(app_tools[app])}")

        if any(a in INSTALL_INSTRUCTIONS for a in app_methods):
            sections.append("")
            sections.append(_("resumen.instrucciones_incluidas"))

        for ln in sections:
            print(_c(ln, _D) if ln.startswith("  ") or ln.startswith("•")
                    else _c(ln, _GR))

    def ensure_activated_for_download(self):
        """La UI pide activación en el resumen si no está activado."""
        if not self.activation_status:
            print(_c("  Necesitás activar la licencia para descargar.", _YE))
            self._ask_activation_code()
        return self.activation_status

    def _make_sheets(self):
        """Reporter de backend (Sheet) para la sesión."""
        from services.sheets_reporter import SheetsReporter
        from app_config import SHEETS_URL
        return SheetsReporter(SHEETS_URL, f"cli-{self.client_id}", self.client_id, APP_VERSION)

    def _send_completed(self, apps=None):
        """Reporta el servicio completado al backend (Sheet)."""
        try:
            apps = apps or self.selected_apps
            method = self.adobe_method or _method_label(apps[0]) if apps else ""
            self._sheets.send_completed(apps=apps, method=method, hwid=self.hwid)
        except Exception:
            pass

    def _send_selection(self, apps):
        """Reporta las apps seleccionadas (confirmadas) a la sesión (Sheet), para
        que al copiar la sesión a Clientes quede la columna 'apps' poblada."""
        try:
            self._sheets.send_selection(apps, self.adobe_method or "")
        except Exception:
            pass

    def _mark_activation_used(self):
        """Marca el código como usado (local síncrono + Sheet async), como la UI."""
        try:
            from services.activation import load_activation_state, mark_activation_used
            _cid, saved_code, saved_max, _hid, _used, _type, _created = load_activation_state(SYOPS_DIR)
        except Exception:
            saved_code, saved_max = None, 3
        if not saved_code:
            return
        try:
            local_ok = mark_activation_used(SYOPS_DIR, self.client_id, self.hwid)
        except Exception:
            local_ok = False
        if not local_ok:
            try:
                self._sheets.send_error(f"Error marcando localmente como usado: {saved_code}")
            except Exception:
                pass
        def _on_use_code_result(sheets_ok):
            if not sheets_ok:
                try:
                    self._sheets.send_error(f"Error marcando en Sheets: {saved_code}")
                except Exception:
                    pass
        try:
            self._sheets.use_code_async(saved_code, self.hwid, saved_max, callback=_on_use_code_result)
        except Exception:
            pass

    def _backend_check(self, sheets, code: str, timeout: int = 90):
        """Consulta el Sheet (backend = única autoridad). None si no conecta."""
        import threading as _t
        result = {}

        def _run():
            try:
                result["data"] = sheets.check_code(code, self.hwid)
            except Exception:
                result["data"] = None

        th = _t.Thread(target=_run, daemon=True)
        th.start()
        th.join(timeout)
        return result.get("data")

    def _ask_activation_code(self):
        import time as _time
        sheets = self._sheets
        try:
            sheets.send_session(get_system_scan_info(), hwid=self.hwid)
        except Exception:
            pass
        _sep()
        print(_c(_B + "  ACTIVACIÓN", _YE))
        _sep()
        print(f"  Enviá tu Cliente ID ({self.client_id}) por WhatsApp a "
              f"{_c(_B + WHATSAPP_DISPLAY, _GR)}")
        print(_c("  El código vence a los pocos minutos; si se agota, pedí otro por WhatsApp.", _D))
        t0 = _time.time()
        while True:
            code = _ask("Código de activación (o 'q' para cancelar)")
            if code.lower() in ("cancelar", "salir"):
                return
            if not code:
                continue
            # 1) El Sheet es la ÚNICA autoridad: valida el código online.
            backend = self._backend_check(sheets, code)
            if not backend or not isinstance(backend, dict):
                left = max(0, 60 - int(_time.time() - t0))
                print(_c(f"  ✗ {_('activacion.sin_conexion')} (restan {left}s)", _RD))
                if left <= 0:
                    print(_c("  Tiempo agotado. Volvé a escribir a WhatsApp.", _RD))
                    t0 = _time.time()
                continue
            status = backend.get("code_status", "")
            msgs = {
                "usado": "activacion.codigo_usado",
                "used": "activacion.codigo_usado",
                "otro_equipo": "activacion.codigo_otro_equipo",
                "other_hwid": "activacion.codigo_otro_equipo",
                "expirado": "activacion.codigo_expirado",
                "expired": "activacion.codigo_expirado",
                "not_found": "activacion.codigo_no_en_sheets",
                "firma_invalida": "activacion.codigo_invalido",
            }
            if status in msgs:
                print(_c(f"  ✗ {_(msgs[status])}", _RD))
                continue
            if not backend.get("available", False):
                print(_c(f"  ✗ {_('activacion.codigo_invalido')}", _RD))
                continue
            # 2) max_apps y tipo los decide el backend; fallback local HMAC.
            code_type = backend.get("type", "standard")
            try:
                max_apps = int(backend.get("max_apps", 0) or 0)
            except (TypeError, ValueError):
                max_apps = 0
            if not max_apps:
                max_apps = 99 if code_type == "adobe_full_pack" else 3
                try:
                    from services.activation import get_activation_max_apps
                    local = get_activation_max_apps(self.client_id, code, self.hwid)
                    if local > 0:
                        max_apps = local
                except Exception:
                    pass
            try:
                from services.activation import save_activation_state
                save_activation_state(SYOPS_DIR, self.client_id, code, max_apps,
                                      hwid=self.hwid, type_value=code_type)
            except Exception:
                pass
            self.activation_status = True
            self.max_apps = max(1, min(max_apps, MAX_APPS))
            self.activation_type = code_type
            try:
                sheets.send_activation(self.client_id, max_apps, code=code, hwid=self.hwid)
            except Exception:
                pass
            print(_c(f"  ✓ {_('activacion.exito', max_apps=self.max_apps)}", _GR))
            return

    def effective_count(self):
        """Delega en el esqueleto (límite con crédito Adobe)."""
        return self.motor.efectivo_conteo()

    # ── Paso 6: descarga ───────────────────────────────────────────
    def run_download(self, output_dir: Path):
        apps = self.selected_apps
        office = self.office_sub_apps
        adobe_patched = self.adobe_patched
        download_apps = build_download_apps(apps, office, adobe_patched)
        if not download_apps:
            print(_c("  Nada descargable con esa selección (instalación manual).", _YE))
            return 0

        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            print(_c("  ⚠ Sin backend de links configurado: no hay catálogo de descargas.", _RD))
            return 0

        from services.download_planner import plan_downloads
        plan = plan_downloads(download_apps, output_dir,
                              self.adobe_method or "macked",
                              link_provider=self._link_provider(),
                              platform="mac" if IS_MAC else "win")
        for w in plan.warnings:
            print(_c(f"  ⚠ {w}", _YE))
        if not plan.tasks:
            print(_c("  No se pudo construir ninguna tarea.", _RD))
            return 0
        self._run_tasks(plan.tasks, output_dir)
        _write_instructions_file(output_dir, list(apps) + office)
        if (output_dir / "instrucciones.txt").exists():
            print(_c(f"  Instrucciones de instalación: {output_dir / 'instrucciones.txt'}", _GR))
        return plan.ok_count

    def _bypass_sirve(self, file_id: str, timeout: int = 8) -> bool:
        """Delega en el esqueleto (app_flow)."""
        from app_flow import bypass_pixeldrain_sirve as _bp
        return _bp(file_id, timeout)

    def _necesita_serializar(self, tasks) -> bool:
        """Delega en el esqueleto (app_flow)."""
        from app_flow import necesita_serializar as _ns
        return _ns(tasks)

    def _run_tasks(self, tasks, output_dir: Path) -> int:
        """Motor de descarga con progreso (compartido por flujo normal y full pack)."""
        _sep()
        print(_c(_B + "  DESCARGA", _CY))
        _sep()
        print(f"  {len(tasks)} archivo(s) a: {output_dir}")
        for t in tasks:
            browser = " [navegador worker]" if t.resolver_callback else ""
            print(f"  • {t.name}  [{t.method}]{browser}")

        from app_config import MAX_CONCURRENT
        # Pixeldrain (cuenta anónima) limita conexiones simultáneas: si una
        # tarea cae a la API directa (ningún bypass la sirve), varias en
        # paralelo reciben 403 (max_concurrent_downloads). Si TODAS se
        # sirven por bypass (otro dominio) no hay límite → paralelo.
        max_concurrent = 1 if self._necesita_serializar(tasks) else MAX_CONCURRENT
        engine = DownloadEngine()
        manager = DownloadManager(engine, max_concurrent)

        def on_progress(name, pct, status, downloaded, total):
            pct = int(pct or 0)
            bar = "#" * (pct // 5) + "." * (20 - pct // 5)
            mb = downloaded / (1024 * 1024)
            total_mb = f"/{total / (1024 * 1024):.0f}MB" if total else ""
            print(f"\r  {name[:26]:<26} [{bar}] {pct:>3}%  {mb:.0f}MB{total_mb}  {status}", end="", flush=True)

        def on_completed(name, success, size):
            print(f"\r  {name[:26]:<26} " +
                  (_c("✓ LISTO", _GR) if success else _c("✗ FALLÓ", _RD)) +
                  (f"  ({size / (1024 * 1024):.1f} MB)" if success else ""))
            if not success:
                try:
                    t = next(x for x in tasks if x.name == name)
                    self._sheets.send_error(
                        f"{name}: {t.error_msg or 'error desconocido'} "
                        f"(status={t.status})")
                except Exception:
                    pass

        manager.task_progress.connect(on_progress)
        manager.task_completed.connect(on_completed)
        for t in tasks:
            manager.add_task(t)

        asyncio.run(manager.start_all())
        print()
        failed = [t for t in tasks if t.status == "failed"]
        print(_c(f"  Finalizado: {len(tasks) - len(failed)}/{len(tasks)} completados.",
                 _GR if not failed else _YE))
        for t in failed:
            print(_c(f"  ✗ {t.name}: {t.error_msg or 'error desconocido'}", _RD))
        return len(tasks) - len(failed)

    # ── Paso 7: final ──────────────────────────────────────────────
    def show_final(self, output: Path | None = None):
        _sep()
        print(_c(_B + "  ¡LISTO!", _GR))
        _sep()
        print("  Tus archivos quedaron en las carpetas indicadas.")
        print("  Seguí las instrucciones de instalación (instrucciones.txt).")
        if self.adobe_patched:
            print(f"  Adobe patched (GenP): {', '.join(self.adobe_patched)}")
        if IS_MAC:
            print()
            print(_c("  macOS: si macOS bloquea una app descargada, hacé clic "
                     "derecho → Abrir.", _D))
        elif IS_WIN:
            print()
            print(_c("  Windows: si Defender marca un archivo, agregá la "
                     "carpeta de descarga a la whitelist.", _D))
        print()
        # La instalación es MANUAL: la asistencia (RustDesk) se ofrece recién
        # acá, después de la descarga, para ayudar a instalar.
        if self.motor.tiene_descargable() and output and _yes_no(
                "¿Querés que soporte te ayude a instalar por videollamada "
                "(RustDesk)?", default="n"):
            self.run_rustdesk(output, confirm=False)
        print()
        print(_c("  Gracias por usar SyopS Prep.", _D))

    # ── Flujo principal ────────────────────────────────────────────
    # ── Adobe Full Pack (licencia adobe_full_pack en macOS) ────────
    def _es_full_pack(self):
        """La licencia adobe_full_pack descarga el paquete completo de Adobe."""
        return self.motor.es_full_pack

    def run_rustdesk(self, output_dir: Path, confirm: bool = True) -> bool:
        """Escanea, pregunta, descarga e instala RustDesk sin Qt.

        Devuelve True si se puede continuar (instalado, ya presente o el
        usuario decidió omitirlo) y False si decide detenerse tras un fallo.
        """
        from services.rustdesk_service import is_rustdesk_installed, download_and_install

        _sep()
        print(_c(_B + "  RUSTDESK — SOPORTE REMOTO", _CY))
        _sep()
        if is_rustdesk_installed():
            print(_c("  ✓ RustDesk ya está instalado. Se continúa.", _GR))
            return True
        print("  RustDesk permite que soporte te ayude de forma remota.")
        if confirm and not _yes_no("¿Querés instalar RustDesk?", default="s"):
            print(_c("  RustDesk omitido. Podés continuar sin soporte remoto.", _D))
            return True

        def progress(name, pct, status, downloaded, total):
            mb = downloaded / (1024 * 1024)
            total_mb = f"/{total / (1024 * 1024):.0f}MB" if total else ""
            print(f"\r  {name:<24} {int(pct):>3}% {mb:.0f}MB{total_mb}  {status}",
                  end="", flush=True)

        try:
            ok, installer = asyncio.run(
                download_and_install(output_dir, progress_callback=progress)
            )
        except Exception as exc:
            ok, installer = False, output_dir / "rustdesk"
            print(f"\n  RustDesk: error controlado ({type(exc).__name__}).")
        print()
        if ok:
            print(_c("  ✓ RustDesk instalado correctamente.", _GR))
            return True
        print(_c(f"  ✗ No se pudo instalar RustDesk ({installer}).", _RD))
        return _yes_no("¿Continuar sin RustDesk?", default="s")

    def run_fullpack(self, show_intro: bool = True):
        """Flujo del Full Pack (igual que la página ADOBE_FULLPACK de la UI):
        sin selección ni preguntas — se descarga el collection AIO completo."""
        from catalog.adobe_helpers import _adobe_full_pack_links
        if show_intro:
            self.show_inicio()
        self.show_scan()
        self.adobe_method = "aio_macked"
        fp_links = _adobe_full_pack_links("aio_macked")
        _sep()
        print(_c(_B + "  ADOBE FULL PACK", _CY))
        _sep()
        for name, _url in fp_links:
            print(f"  • {name}")
        print(_c(f"  ({len(ADOBE_APPS)} apps de Adobe incluidas en el paquete)", _D))
        print()
        scan = get_system_scan_info()
        for ln in _compatibility_lines(scan, list(ADOBE_APPS)):
            print(_c(ln, _GR if ("✓" in ln) else (_RD if "✗" in ln else _YE)))
        print()
        print(_c("  Método: AIO MacKed", _GR))
        print()
        if not _yes_no("¿Confirmás la descarga del Full Pack?", default="s"):
            print(_c("  Cancelado.", _YE))
            return
        if not self.ensure_activated_for_download():
            print(_c("  Sin activación no se puede descargar. Volvé a ejecutarlo.", _RD))
            return
        output = SYOPS_DIR / "adobe_full_pack"
        output.mkdir(parents=True, exist_ok=True)
        from services.download_planner import plan_downloads
        plan = plan_downloads([], output, "aio_macked", adobe_fullpack=True,
                              link_provider=self._link_provider(),
                              platform="mac" if IS_MAC else "win")
        self._run_tasks(plan.tasks, output)
        self._send_completed()
        self._mark_activation_used()
        self.show_final(output)

    # ── Efectos (protocolo app_flow.Efectos) ──────────────────────
    # El motor decide QUÉ efecto se necesita (efectos_necesarios); estas
    # implementaciones deciden CÓMO presentarlo en el terminal.
    def pedir_activacion(self) -> bool:
        return self.ensure_activated_for_download()

    def descargar(self, output_dir: Path, adobe_fullpack: bool = False) -> int:
        if adobe_fullpack:
            from services.download_planner import plan_downloads
            plan = plan_downloads([], output_dir, "aio_macked", adobe_fullpack=True,
                                  link_provider=self._link_provider(),
                                  platform="mac" if IS_MAC else "win")
            self._run_tasks(plan.tasks, output_dir)
            return plan.ok_count
        return self.run_download(output_dir)

    def reportar(self, evento: str, **kw) -> None:
        if evento == "completed":
            self._send_completed()
            self._mark_activation_used()
        elif evento == "downloads":
            try:
                self._sheets.send_downloading(list(self.selected_apps))
            except Exception:
                pass

    def whitelist(self) -> None:
        if IS_WIN:
            import threading as _threading
            from system.hardware import whitelist_defender
            _threading.Thread(target=whitelist_defender,
                              args=(SYOPS_DIR,), daemon=True).start()

    def instrucciones(self, output_dir: Path) -> None:
        _write_instructions_file(output_dir, list(self.selected_apps) + self.office_sub_apps)

    def _ejecutar_efectos(self, output_dir: Path) -> bool:
        """Ejecuta los efectos que el motor decide (ordena por su lista)."""
        n_ok = 0
        for nombre in self.motor.efectos_necesarios():
            if nombre == "instrucciones":
                self.instrucciones(output_dir)
            elif nombre == "descargar":
                n_ok = self.descargar(output_dir)
            elif nombre == "whitelist":
                self.whitelist()
            elif nombre == "reportar":
                if n_ok or not self.motor.tiene_descargable():
                    self.reportar("completed")
        return True

    def _seleccion(self) -> bool:
        """Selección multi-categoría compartida (guiado / vista)."""
        self.show_scan()
        self.choose_category()
        while True:
            self.choose_apps()
            if len(self.selected_apps) >= self.max_apps:
                print(_c(f"  Llegaste al máximo de {self.max_apps} apps de tu plan.", _GR))
                break
            if not _yes_no("¿Agregar programas de otra categoría?", default="n"):
                break
            self.choose_category()
        self.ask_adobe_question()
        self.choose_adobe_method_if_needed()
        return self.show_resumen()

    def _run_guided(self):
        """Rama 1: selección → activación → descarga (flujo completo)."""
        if not self._seleccion():
            print(_c("  Re-ejecutá el asistente para reiniciar la selección.", _D))
            return
        # La activación se solicita DESPUÉS del resumen confirmado
        # (misma lógica que la UI: la descarga queda bloqueada hasta activar).
        if not self.ensure_activated_for_download():
            print(_c("  Sin activación no se puede descargar. Volvé a ejecutarlo.", _RD))
            return
        if self.effective_count() > self.max_apps:
            print(_c(f"  ✗ Superás el límite de {self.max_apps} apps de tu plan.", _RD))
            return
        # Selección sin nada descargable: confirmar y finalizar (como la UI).
        if not self.motor.tiene_descargable():
            print(_c("  Tu selección no requiere descargas (instalación manual).", _YE))
            if not _yes_no("¿Confirmás la selección de todas formas?", default="s"):
                print(_c("  Re-ejecutá el asistente para cambiar la selección.", _D))
                return
        output = SYOPS_DIR / (self.adobe_method or "http")
        output.mkdir(parents=True, exist_ok=True)
        if not self._ejecutar_efectos(output):
            return
        self.show_final(output)

    def _offer_self_delete(self):
        """Al salir, ofrece borrar SyopS del sistema (wizard + activación +
        descargas). Nunca toca un repo git (modo desarrollo).
        """
        if not _yes_no("\n¿Borrar SyopS del sistema? (elimina el wizard, la "
                       "activación y lo descargado)", default="n"):
            return
        import shutil
        wiz = Path(__file__).resolve().parent
        # Seguridad: no borrar jamás un repo en desarrollo.
        if (wiz / ".git").exists() or wiz.name.endswith("Wizard"):
            print(_c("  ✗ Modo desarrollo: no se autoelimina el repo.", _RD))
            return
        targets = [wiz]
        if SYOPS_DIR and SYOPS_DIR.resolve() != wiz.resolve():
            targets.append(SYOPS_DIR)
        print(_c("  ✓ Borrando SyopS: " + ", ".join(str(t) for t in targets), _GR))
        for t in targets:
            try:
                if IS_WIN:
                    import subprocess
                    args = ["cmd", "/c",
                            "@timeout /t 2 /nobreak >nul & rmdir /s /q \"" + str(t) + "\""]
                    subprocess.Popen(args, shell=False,
                                     creationflags=0x08000000 | 0x00000008)  # detach + no window
                else:
                    shutil.rmtree(t, ignore_errors=True)
            except Exception:
                pass
        print(_c("  Gracias por usar SyopS. El equipo quedó limpio.", _D))

    def _precheck_backend(self):
        """Comprueba temprano si el backend de links responde (aviso a tiempo)."""
        import urllib.request as _urlreq
        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            return
        try:
            with _urlreq.urlopen(server, timeout=90) as resp:
                resp.read(64)
        except Exception:
            print(_c("  ⚠ No se pudo contactar al backend de links: las "
                     "descargas fallarán.", _YE))
            print(_c("    Revisá tu conexión a internet y reintentá.", _YE))
        else:
            print(_c("  ✓ Backend de links disponible.", _GR))
        print()

    def _check_update(self):
        """Detecta y ofrece aplicar una versión más nueva (autoactualización)."""
        try:
            from services.auto_update import check_for_update, apply_update
        except Exception:
            return
        hay_update, nueva, actual = check_for_update()
        if not hay_update:
            return
        _sep()
        print(_c(_B + "  ACTUALIZACIÓN DISPONIBLE", _YE))
        print(f"  Versión actual: {actual} → nueva: {nueva}")
        print("  La actualización no borra tus datos, activación ni descargas.")
        _sep()
        if _yes_no("¿Actualizar ahora?", default="n"):
            ok, msg = apply_update()
            print(_c(("  ✓ " if ok else "  ✗ ") + msg, _GR if ok else _RD))
            if ok:
                _ask("Presioná Enter para cerrar y reiniciar con la versión nueva")
                raise SystemExit(0)
        else:
            print(_c("  Te quedás con la versión actual por ahora.", _D))
        print()

    def run(self):
        """Flujo lineal (como antes): inicio → guiado → fin."""
        try:
            self._sheets = self._make_sheets()
            self.load_activation()
            self._check_update()
            self._precheck_backend()
            # Licencia Full Pack en macOS: flujo dedicado (como la UI).
            if self._es_full_pack():
                self.run_fullpack()
                return
            self.show_inicio()
            self._run_guided()
            # Al cerrar el wizard, ofrecer autoeliminación.
            self._offer_self_delete()
        except WizardCancelled:
            print(_c("\n  Cancelado.", _YE))
            sys.exit(0)
        except KeyboardInterrupt:
            print(_c("\n  Cancelado.", _YE))
            sys.exit(1)


if __name__ == "__main__":
    Wizard().run()
