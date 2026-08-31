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
import sys
import time
from pathlib import Path


from wizard_ui import (
    WizardCancelled, _ask, _c, _code_type_for, _flush_pending_input,
    _html_to_text, _list_apps, _method_label, _parse_numbers, _pick_adobe_method,
    _pick_numbers, _platform_apps, _sep, _wrap_lines, _yes_no,
    _OS_NAME, _B, _D, _CY, _GR, _RD, _R, _YE, _COLOR_OK,
)
from wizard_download import DownloadMixin, UpdateMixin
from wizard_activation import ActivationMixin

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
from services.server_catalog import fetch_catalog_index, build_catalog
from system.specs import _format_specs_line, _compatibility_lines
from catalog.adobe import ADOBE_METHODS
from catalog.adobe_helpers import _adobe_tools_for_method
from services.seleccion_logic import build_download_apps
from services.download_engine import DownloadEngine
from services.download_manager import DownloadManager
from services.download_resolvers import _write_instructions_file
from system.hardware import get_hwid, get_machine_id, get_system_scan_info
from i18n import _





class Wizard(DownloadMixin, UpdateMixin, ActivationMixin):
    """Vista de terminal sobre el esqueleto app_flow (FlujoMotor).

    El estado y las reglas viven en self.motor; este wizard solo se ocupa
    de la presentación (input/output). Las propiedades delegadas mantienen
    compatibilidad con los tests y con el código existente.
    """

    def __init__(self):
        from app_flow import FlujoMotor
        self.client_id = get_machine_id()
        self.hwid = get_hwid()
        self.current_page = "inicio"
        self._sheet_methods = {}
        self.motor = FlujoMotor(
            self.client_id, self.hwid, IS_MAC, IS_WIN,
            catalogo=self._load_catalog(),
        )
        self._catalog = self.motor.catalogo

    def _load_catalog(self):
        """Catálogo de categorías servido por la hoja `Links`.

        Fetch de `get_catalog_index` (solo nombres/categorías, sin URLs).
        Si el backend no responde, no trae nada para este SO o el fetch está
        deshabilitado (SYOPS_NO_CATALOG_FETCH), cae al catálogo local.
        """
        self._sheet_methods = {}
        self._sheet_platforms = {}
        if os.environ.get("SYOPS_NO_CATALOG_FETCH"):
            return None
        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        try:
            items = fetch_catalog_index(server, timeout=10)
        except Exception:
            items = None
        if items is None:
            return None
        os_key = "mac" if IS_MAC else "win"
        from catalog.data import SOFTWARE_CATEGORIES
        catalog, methods, platforms = build_catalog(items, os_key,
                                                    SOFTWARE_CATEGORIES)
        self._sheet_methods = methods
        self._sheet_platforms = platforms
        from services.download_resolvers import set_sheet_platforms
        set_sheet_platforms(platforms)
        return catalog

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
        self.current_page = "inicio"
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
        self.current_page = "diagnostico"
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
    def _cat_label(self, key) -> str:
        """Label de pantalla de una categoría (directo del sheet o key)."""
        src = self._catalog or SOFTWARE_CATEGORIES
        info = src.get(key, {}) or {}
        return info.get("label") or key

    def choose_category(self):
        self.current_page = "categoria"
        src = self._catalog or SOFTWARE_CATEGORIES
        cats = [(k, v) for k, v in src.items()
                if k != "all" and v.get("apps")]
        _sep()
        print(_c(_B + "  ELEGÍ UNA CATEGORÍA", _CY))
        _sep()
        from app_flow.flujo import platform_apps
        for i, (key, info) in enumerate(cats, 1):
            label = info.get("label") or key
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
        self.current_page = "adobe_method"
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
        _list_apps(adobe_selected, methods=self._sheet_methods)
        nums = _pick_numbers(len(adobe_selected), prompt="¿Cuáles ya tenés? (0 = ninguno)")
        self.motor.marcar_adobe_patched([adobe_selected[i - 1] for i in nums])
        print(_c(f"  ↳ Patcheados con GenP: {', '.join(self.adobe_patched) or 'ninguno'}", _D))
        print()

    def choose_apps(self):
        self.current_page = "seleccion"
        """Elige apps de la categoría actual ACUMULANDO sobre la selección
        previa (multi-categoría), respetando el límite del plan."""
        while True:
            src = self._catalog or SOFTWARE_CATEGORIES
            all_apps = list(src[self.cat]["apps"])
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

        def _render_menu():
            """Imprime el menú de la categoría (título, elegidos, lista y leyenda).
            Se re-ejecuta tras quitar programas para que la lista se actualice."""
            _sep()
            print(_c(_B + "  SELECCIÓN DE PROGRAMAS", _CY))
            print(_c(f"  Elegidos: {len(self.selected_apps)}/{self.max_apps} | "
                     f"plataforma: {_OS_NAME} | categoría actual: "
                     f"{self._cat_label(self.cat)}", _D))
            _sep()
            _list_apps(apps, already=self.selected_apps, methods=self._sheet_methods)
            if hidden:
                print(_c(f"  (ocultos por no estar disponibles en {_OS_NAME}: "
                         f"{', '.join(hidden)})", _D))
            # Leyenda de comandos (se muestra al llegar a esta sección).
            print(_c(_("seleccion.cli_comandos"), _D))
            print(_c(_("seleccion.cli_hint_numeros"), _D))
            if self.selected_apps:
                print(_c(_("seleccion.cli_hint_r"), _D))
            print(_c(_("seleccion.cli_hint_0"), _D))
            print(_c(_("seleccion.cli_hint_q"), _D))
            print()

        _render_menu()

        # Menú: números = agregar, "0" = salir de esta categoría,
        # "r" = quitar programas ya elegidos (deseleccionar).
        while True:
            remaining = max(0, self.max_apps - len(self.selected_apps))
            prompt = _("seleccion.cli_prompt_base")
            if self.selected_apps:
                prompt += _("seleccion.cli_prompt_r")
            prompt += ")"
            raw = _ask(prompt)
            low = raw.strip().lower()
            if low == "0":
                return "salir"
            if low in ("r", "quitar"):
                self._quitar_apps()
                # Re-dibujar el menú: la selección cambió y la lista debe verse
                # actualizada (el input ya no se desfasa del estado).
                _render_menu()
                continue
            nums = _parse_numbers(raw, len(apps))
            if nums is None:
                print(_c(_("seleccion.cli_hint_numeros_invalidos", n=len(apps)), _YE))
                continue
            if not nums:
                print(_c(_("seleccion.cli_hint_min_uno"), _YE))
                continue
            if len(nums) > remaining:
                print(_c(_("seleccion.cli_hint_restante", remaining=remaining), _YE))
                continue
            new_apps = [apps[i - 1] for i in nums]
            self.motor.agregar_apps(new_apps)
            print(_c(_("seleccion.cli_ya_actual", sel=", ".join(self.selected_apps)), _GR))
            print()

            # Requisitos mínimos de las apps recién elegidas (como specs_info).
            self._show_selected_specs(new_apps)

            # Office → sub-apps (misma página OFFICE de la UI)
            if OFFICE_PARENT in new_apps:
                self.choose_office()
            break
        return None

    def _quitar_apps(self):
        """Quita programas de la selección acumulada (deseleccionar)."""
        sel = list(self.selected_apps)
        if not sel:
            print(_c(_("seleccion.cli_quitar_vacio"), _YE))
            return
        _sep()
        print(_c(_B + _("seleccion.cli_quitar_titulo"), _CY))
        _sep()
        _list_apps(sel, methods=self._sheet_methods)
        print()
        while True:
            raw = _ask(_("seleccion.cli_quitar_prompt"))
            if raw.strip() == "0":
                print(_c(_("seleccion.cli_quitar_sin_cambios"), _D))
                return
            nums = _parse_numbers(raw, len(sel))
            if nums is None:
                print(_c(_("seleccion.cli_hint_numeros_invalidos", n=len(sel)), _YE))
                continue
            break
        removidos = self.motor.remover_apps([sel[i - 1] for i in nums])
        print(_c(_("seleccion.cli_quitar_hecho", rem=", ".join(removidos)), _YE))
        print(_c(_("seleccion.cli_ya_actual", sel=", ".join(self.selected_apps) or "ninguno"), _D))
        print()

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
        _list_apps(office_list, methods=self._sheet_methods)
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
        self.current_page = "resumen"
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
            self.selected_apps = []
            return False
        self._send_selection(display)
        return True

    def _show_method_sections(self):
        """Método de descarga, apps Adobe con versión y tools (como la UI)."""
        from catalog.adobe_helpers import _adobe_best_link, _adobe_tools_for_method
        from catalog.tools import TOOL_APPS, _app_tools_for_app
        from services.seleccion_logic import describe_method
        from services.download_link_provider import fetch_tools_map
        from app_config import SHEETS_URL

        sheet_items = fetch_tools_map(SHEETS_URL) if SHEETS_URL else []

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
                app_methods[a] = _method_label(a, self._sheet_methods)
        for office_app in (self.office_sub_apps or []):
            if office_app not in app_methods:
                app_methods[office_app] = "http"

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
            tool_names = [name for name, _ in _adobe_tools_for_method(
                self.adobe_method, sheet_items)]
            if tool_names:
                sections.append(_("resumen.tools_linea", tools=", ".join(tool_names)))

        if self.adobe_patched:
            sections.append(_("resumen.app_para_activar",
                              app=", ".join(self.adobe_patched)))

        if tools:
            sections.append(_("resumen.herramientas_seleccionadas"))
            for app, m in tools.items():
                sections.append(f"  • {app}")

        # Tools por app (non-Adobe): deduplicar entre apps
        app_tools = {}
        seen_tools = set()
        for app in app_methods:
            if app in ADOBE_APPS:
                continue
            for tool in _app_tools_for_app(app, sheet_items):
                tool_name = tool.get("name", tool) if isinstance(tool, dict) else tool
                if tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    app_tools.setdefault(app, []).append(tool_name)
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

    def effective_count(self):
        """Delega en el esqueleto (límite con crédito Adobe)."""
        return self.motor.efectivo_conteo()

    # ── Paso 6: descarga ───────────────────────────────────────────
    def run(self):
        """Flujo lineal (como antes): inicio → guiado → fin."""
        import threading
        self.current_page = "inicio"
        self._update_applied = False
        try:
            self._sheets = self._make_sheets()
            self.load_activation()
            t1 = threading.Thread(target=self._check_update)
            t2 = threading.Thread(target=self._precheck_backend)
            t1.start(); t2.start()
            t2.join(timeout=15)
            t1.join()
            if self._update_applied:
                if IS_WIN:
                    print(_c("\n  Cerrá y reabrí la terminal para usar la nueva versión.", _YE))
                raise SystemExit(0)
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


def _elevate_if_needed() -> None:
    """Pide permisos de administrador UNA vez, al inicio del wizard.

    macOS/Linux: re-ejecuta el wizard con sudo (pide la clave una sola vez;
    el resto del flujo corre como root y no vuelve a pedirla para instalar
    WARP, RustDesk, gatekeeper, hdiutil, etc.).
    Windows: relanza con UAC (system.hardware.ensure_admin).
    Desactivable con SYOPS_NO_ELEVATE=1 (desarrollo/tests).
    """
    if os.environ.get("SYOPS_NO_ELEVATE", "") in ("1", "true", "True"):
        return
    if sys.platform == "win32":
        try:
            from system.hardware import ensure_admin
            ensure_admin()
        except Exception:
            pass
        return
    # POSIX: ya root → no hace falta elevar.
    try:
        if os.geteuid() == 0:
            return
    except AttributeError:
        return
    script = str(Path(__file__).resolve())
    try:
        os.execv("/usr/bin/sudo", ["sudo", sys.executable, script, *sys.argv[1:]])
    except Exception:
        # Si no se puede elevar (sudo cancelado), sigue sin privilegios.
        print(_c("  ⚠ Sin permisos de administrador: algunas instalaciones "
                 "(WARP, RustDesk, gatekeeper) podrían pedir la clave luego.", _YE))


if __name__ == "__main__":
    try:
        from services.auto_update import apply_pending_update
        if apply_pending_update():
            import subprocess
            python = sys.executable
            script = str(Path(__file__).resolve())
            subprocess.Popen([python, script],
                             cwd=str(Path(__file__).resolve().parent))
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as _e:
        import traceback
        traceback.print_exc()
    _elevate_if_needed()
    Wizard().run()
