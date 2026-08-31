#!/usr/bin/env python3
"""ActivationMixin — métodos de activación del Wizard (extraídos de syops_wizard.py).

Componible en ``class Wizard``. Usa ``self`` normalmente; las dependencias
de módulo se importan acá (ruff F821 si falta algo).
"""

import os
import time
from pathlib import Path

from wizard_ui import (
    WizardCancelled, _ask, _c, _code_type_for, _flush_pending_input,
    _html_to_text, _list_apps, _method_label, _parse_numbers,
    _pick_adobe_method, _pick_numbers, _platform_apps, _sep, _wrap_lines,
    _yes_no, _OS_NAME, _B, _D, _CY, _GR, _RD, _R, _YE, _COLOR_OK,
)
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

class ActivationMixin:
    def ensure_activated_for_download(self):
        """La UI pide activación en el resumen si no está activado."""
        if os.environ.get("SYOPS_DEMO", "") in ("1", "true", "True"):
            self.activation_status = "standard"
            return True
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
            method = self.adobe_method or _method_label(apps[0], self._sheet_methods) if apps else ""
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

    def _backend_check(self, sheets, code: str, timeout: int = 20):
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
