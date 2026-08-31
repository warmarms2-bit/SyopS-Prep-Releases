#!/usr/bin/env python3
"""Mixins de descarga y actualización del Wizard (extraídos de syops_wizard.py).

Los métodos se definen en el mixin y se componen en ``class Wizard``. Usan
``self`` normalmente; las dependencias de módulo se importan acá (ver
ruff F821 si algo falta).
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from wizard_ui import (
    WizardCancelled, _ask, _c, _flush_pending_input, _html_to_text,
    _list_apps, _method_label, _parse_numbers, _pick_adobe_method,
    _pick_numbers, _platform_apps, _sep, _wrap_lines, _yes_no,
    _OS_NAME, _B, _D, _CY, _GR, _RD, _R, _YE, _COLOR_OK,
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

class DownloadMixin:
    def run_download(self, output_dir: Path):
        if os.environ.get("SYOPS_DEMO", "") in ("1", "true", "True"):
            return self._run_download_demo(output_dir)
        apps = self.selected_apps
        office = self.office_sub_apps
        adobe_patched = self.adobe_patched
        download_apps = build_download_apps(apps, office, adobe_patched, self._sheet_methods)
        if not download_apps:
            print(_c("  Nada descargable con esa selección (instalación manual).", _YE))
            return 0

        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            print(_c("  ⚠ Sin backend de links configurado: no hay catálogo de descargas.", _RD))
            return 0

        from services.download_planner import plan_downloads
        from services.download_link_provider import fetch_tools_map
        from app_config import SHEETS_URL
        sheet_items = fetch_tools_map(SHEETS_URL) if SHEETS_URL else []
        plan = plan_downloads(download_apps, output_dir,
                              self.adobe_method or "macked",
                              link_provider=self._link_provider(),
                              platform="mac" if IS_MAC else "win",
                              sheet_items=sheet_items)
        for w in plan.warnings:
            print(_c(f"  ⚠ {w}", _YE))
        if not plan.tasks:
            print(_c("  No se pudo construir ninguna tarea.", _RD))
            return 0

        # Seguridad / IP: con TorBox activo el cliente NUNCA entra al swarm
        # (los peers ven la IP de TorBox, no la tuya), así que WARP queda
        # DESACTIVADO y lo avisamos explícito. Sin TorBox, si hay torrent
        # directo se activa WARP automáticamente para no exponer la IP real.
        from services.torbox_provider import torbox_enabled
        from services.warp_service import ensure_warp, needs_torrent
        if torbox_enabled():
            if plan.tasks:
                print(_c(_B + "  TorBox activo → WARP desactivado: el cliente no "
                              "entra al swarm (los peers ven la IP de TorBox, no "
                              "la tuya).", _CY))
        elif needs_torrent(plan.tasks):
            print(_c(_B + "  Seguridad: hay descargas por torrent; activando "
                          "WARP (oculta tu IP real a los peers)…", _CY))
            ok, msg = ensure_warp()
            print(_c(f"  {'✓' if ok else '✗'} {msg}",
                     _GR if ok else _RD))
            if not ok:
                print(_c("  ⚠ Continuando sin WARP: tu IP real quedará "
                         "expuesta a los peers del torrent.", _YE))

        self._run_tasks(plan.tasks, output_dir)
        _write_instructions_file(output_dir, list(apps) + office)
        if (output_dir / "instrucciones.txt").exists():
            print(_c(f"  Instrucciones de instalación: {output_dir / 'instrucciones.txt'}", _GR))
        return plan.ok_count

    def _run_download_demo(self, output_dir: Path) -> int:
        """Modo demo (SYOPS_DEMO=1, solo para la UI web de pruebas): simula
        la descarga de la selección sin backend ni archivos reales."""
        import time as _time
        apps = self.selected_apps
        if not apps:
            print(_c("  Nada descargable con esa selección (instalación manual).", _YE))
            return 0
        self.current_page = "descarga"
        _sep()
        print(_c(_B + "  DESCARGA (MODO DEMO)", _CY))
        _sep()
        print(f"  {len(apps)} archivo(s) simulado(s) en: {output_dir}")
        for app in apps:
            print(f"  • {app}  [http]")
        print()
        for i, app in enumerate(apps, 1):
            print(f"  ▸ Descargando {app}…")
            for pct in range(0, 101, 10):
                bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                print(f"\r  [{pct:3d}%] {bar}", end="", flush=True)
                _time.sleep(0.15)
            print()
            print(f"  [OK] {app} completado (demo)")
        print(_c(f"\n  ✓ Descargas completadas ({len(apps)}) en modo demo.", _GR))
        return len(apps)

    def _bypass_sirve(self, file_id: str, timeout: int = 8) -> bool:
        """Delega en el esqueleto (app_flow)."""
        from app_flow import bypass_pixeldrain_sirve as _bp
        return _bp(file_id, timeout)

    def _necesita_serializar(self, tasks) -> bool:
        """Delega en el esqueleto (app_flow)."""
        from app_flow import necesita_serializar as _ns
        return _ns(tasks)

    def _run_tasks(self, tasks, output_dir: Path) -> int:
        self.current_page = "descarga"
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

        _started: set[str] = set()
        _last_pct: dict[str, int] = {}
        _last_t: dict[str, float] = {}

        def on_progress(name, pct, status, downloaded, total):
            if name not in _started:
                print(f"\n  ▸ Descargando {name}…")
                _started.add(name)
            pct = int(pct or 0)
            # En terminal interactiva se redibuja siempre (barra animada).
            # En pipe/logs solo si cambió ≥2% o pasaron 0.5s: evita el flood
            # de ~15 líneas/s al volcar a un archivo.
            last_pct = _last_pct.get(name)
            if not sys.stdout.isatty():
                if last_pct is None or (pct - last_pct) < 2:
                    if time.time() - _last_t.get(name, 0.0) < 0.5:
                        return
            _last_pct[name] = pct
            _last_t[name] = time.time()
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
                        f"(status={t.status}, url={t.url_or_magnet})")
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
            print(_c(f"  ✗ {t.name}: {t.error_msg or 'error desconocido'} "
                     f"[url={t.url_or_magnet}]", _RD))
        print(_c(f"  Archivos en: {output_dir}", _GR))
        return len(tasks) - len(failed)

    # ── Paso 7: final ──────────────────────────────────────────────
    def show_final(self, output: Path | None = None):
        self.current_page = "final"
        _sep()
        print(_c(_B + "  ¡LISTO!", _GR))
        _sep()
        print(f"  Tus archivos están en: {output or Path.cwd()}")
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
        if output and _yes_no(
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
        self.current_page = "adobe_fullpack"
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
        for nombre in self.motor.efectos_necesarios(self._sheet_methods):
            if nombre == "instrucciones":
                self.instrucciones(output_dir)
            elif nombre == "descargar":
                n_ok = self.descargar(output_dir)
            elif nombre == "whitelist":
                self.whitelist()
            elif nombre == "reportar":
                if n_ok or not self.motor.tiene_descargable(self._sheet_methods):
                    self.reportar("completed")
        return True

    def _seleccion(self) -> bool:
        """Selección multi-categoría compartida (guiado / vista)."""
        self.show_scan()
        while True:
            self.selected_apps = []
            self.adobe_patched = []
            self.office_sub_apps = []
            self.cat = None
            self.choose_category()
            while True:
                salio = self.choose_apps()
                if salio == "salir":
                    self.choose_category()
                    continue
                if len(self.selected_apps) >= self.max_apps:
                    print(_c(f"  Llegaste al máximo de {self.max_apps} apps de tu plan.", _GR))
                    break
                if not _yes_no("¿Agregar programas de otra categoría?", default="n"):
                    break
                self.choose_category()
            self.ask_adobe_question()
            self.choose_adobe_method_if_needed()
            if self.show_resumen():
                return True
            print(_c("  Reiniciando selección...", _YE))

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
        if not self.motor.tiene_descargable(self._sheet_methods):
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
        """Al salir, ofrece borrar SyopS del sistema: el tool (wizard) y la
        activación. NO borra lo descargado / los instaladores: eso se queda
        con el cliente. Nunca toca un repo git (modo desarrollo).
        """
        if not _yes_no("\n¿Borrar SyopS del sistema? (elimina el wizard y la "
                       "activación; tus descargas/instaladores se quedan con vos)",
                       default="n"):
            return
        import shutil
        wiz = Path(__file__).resolve().parent
        # Seguridad: no borrar jamás un repo en desarrollo.
        if (wiz / ".git").exists() or wiz.name.endswith("Wizard"):
            print(_c("  ✗ Modo desarrollo: no se autoelimina el repo.", _RD))
            return
        print(_c("  ✓ Borrando el asistente SyopS: " + str(wiz), _GR))
        try:
            if IS_WIN:
                import subprocess
                args = ["cmd", "/c",
                        "@timeout /t 2 /nobreak >nul & rmdir /s /q \"" + str(wiz) + "\""]
                subprocess.Popen(args, shell=False,
                                 creationflags=0x08000000 | 0x00000008)  # detach + no window
            else:
                shutil.rmtree(wiz, ignore_errors=True)
        except Exception:
            pass
        # Borrar SOLO la licencia (.activated de SYOPS_DIR), conservando las
        # descargas/instaladores (carpetas <método> dentro de SYOPS_DIR).
        if SYOPS_DIR and (SYOPS_DIR / ".activated").exists():
            try:
                (SYOPS_DIR / ".activated").unlink(missing_ok=True)
                print(_c("  ✓ Licencia desactivada.", _GR))
            except Exception:
                pass
        print(_c("  Gracias por usar SyopS. El asistente quedó eliminado; "
                 "tus descargas se conservan.", _D))


class UpdateMixin:
    def _precheck_backend(self):
        """Comprueba temprano si el backend de links responde (aviso a tiempo)."""
        import urllib.request as _urlreq
        server = (os.environ.get("SYOPS_LINK_SERVER", "").strip()
                  or LINK_SERVER_URL).strip()
        if not server:
            return
        try:
            with _urlreq.urlopen(server, timeout=10) as resp:
                resp.read(64)
        except Exception:
            print(_c("  ⚠ No se pudo contactar al backend de links: las "
                     "descargas fallarán.", _YE))
            print(_c("    Revisá tu conexión a internet y reintentá.", _YE))
        else:
            print(_c("  ✓ Backend de links disponible.", _GR))
        print()

    def _check_update(self):
        # En el binario PORTABLE (PyInstaller, sys.frozen) NO se auto-actualiza:
        # el update baja el bundle de fuente, que un binario congelado no puede
        # aplicar. El portable se actualiza descargando el portable nuevo.
        if getattr(sys, "frozen", False):
            return
        try:
            from services.auto_update import check_for_update, apply_update
        except Exception:
            return
        import time
        # En la UI web no se auto-aplica el update (modifica archivos en uso).
        if os.environ.get("SYOPS_NO_UPDATE", "") in ("1", "true", "True"):
            return
        cooldown_file = SYOPS_DIR / ".update_cooldown"
        if cooldown_file.exists():
            try:
                last = float(cooldown_file.read_text())
                if time.time() - last < 30:
                    return
            except Exception:
                pass
        hay_update, nueva, actual = check_for_update()
        if not hay_update:
            return
        _sep()
        print(_c(_B + "  ACTUALIZACIÓN DISPONIBLE", _YE))
        print(f"  Versión actual: {actual} → nueva: {nueva}")
        print("  Actualizando automáticamente...")
        _sep()
        ok, msg = apply_update()
        print(_c(("  ✓ " if ok else "  ✗ ") + msg, _GR if ok else _RD))
        if ok:
            try:
                SYOPS_DIR.mkdir(parents=True, exist_ok=True)
                cooldown_file.write_text(str(time.time()))
            except Exception:
                pass
            self._update_applied = True
