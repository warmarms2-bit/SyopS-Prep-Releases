"""Esqueleto del flujo de SyopS Prep (app_flow).

La lógica de decisión del asistente vive ACÁ, agnóstica de presentación:
sin Qt, sin input(), sin print(). Tanto el wizard de terminal como la UI
(syops_wizard.py / ui/navigation_controller.py) son dos VISTAS sobre el
mismo esqueleto: consultan el estado, aplican acciones y ejecutan los
EFECTOS (descargar, reportar al Sheet, pedir activación) a través de una
interfaz que cada vista implementa.

Lo que centraliza:
  - Estado del flujo (categoría, selección, sub-apps, método Adobe,
    activación, límite, etapa actual).
  - Reglas de plataforma (apps disponibles por SO, Office/combo).
  - Reglas de Adobe (pregunta GenP solo Windows; métodos que cubren
    TODAS las apps elegidas; preselección del recomendado).
  - Límite del plan (con crédito Adobe) y selección multi-categoría.
  - Transiciones de etapa (máquina de estados del flujo).
"""

from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from catalog.base import IS_MAC, IS_WIN
from app_config import DEFAULT_APPS, MAX_APPS
from catalog.data import ADOBE_APPS, OFFICE_PARENT
from catalog.categorias import OFFICE_APPS, OFFICE_CORE_APPS
from catalog.tools import COMBO_TOOLS
from catalog.adobe import ADOBE_METHODS
from catalog.adobe_helpers import (
    _adobe_apps_supported_by_method, _adobe_count_for_limit,
)
from services.download_resolvers import _is_app_available_on_platform
from services.seleccion_logic import has_downloadable

__all__ = [
    "Etapa", "FlujoEstado", "FlujoMotor", "Efectos",
    "platform_apps", "metodos_compatibles", "preseleccionar_metodo",
]


class Etapa(Enum):
    """Etapas del flujo (mismo orden que la UI)."""
    INICIO = "inicio"
    SCAN = "scan"
    CATEGORIA = "categoria"
    SELECCION = "seleccion"
    OFFICE = "office"
    ADOBE_METHOD = "adobe_method"
    ADOBE_FULLPACK = "adobe_fullpack"
    RESUMEN = "resumen"
    DESCARGA = "descarga"
    FINAL = "final"


class FlujoEstado:
    """Estado mutable del flujo (lo que avanza la sesión)."""

    def __init__(self):
        self.categoria = None
        self.seleccion = []           # apps acumuladas (multi-categoría)
        self.office_sub = []          # sub-apps de Office elegidas
        self.adobe_patched = []       # Adobe ya instalados (GenP, solo Windows)
        self.adobe_method = None      # método Adobe (macOS)
        self.max_apps = DEFAULT_APPS  # límite del plan
        self.activado = False
        self.tipo = "standard"        # standard | adobe_full_pack
        self.etapa = Etapa.INICIO


@runtime_checkable
class Efectos(Protocol):
    """Acciones de salida que cada vista implementa (terminal o UI).

    El esqueleto decide QUÉ hacer; la vista decide CÓMO (mostrar,
    ejecutar motor de descargas, consultar al usuario, reportar).
    """

    def pedir_activacion(self) -> bool:
        """Pide el código y valida con el backend; True si quedó activado."""
        ...

    def descargar(self, output_dir: Path, adobe_fullpack: bool = False) -> int:
        """Ejecuta la descarga de la selección actual. Devuelve nº de OK."""
        ...

    def reportar(self, evento: str, **kw) -> None:
        """Reporta al backend (Sheet): session/selection/activated/completed."""
        ...

    def whitelist(self) -> None:
        """Aplica la whitelist de Windows Defender (solo Windows)."""
        ...

    def instrucciones(self, output_dir: Path) -> None:
        """Escribe instrucciones.txt de instalación."""
        ...


# ── Reglas puras (sin estado) ─────────────────────────────────────


def platform_apps(apps: list, is_mac: bool = IS_MAC, is_win: bool = IS_WIN) -> list:
    """Filtra las apps con link para el SO actual (misma regla que la UI).

    'Office' (padre) y los combos (ej. 'Mole + Talon') no tienen link
    directo: se expanden en partes, así que se consideran disponibles si
    ALGUNA de sus partes lo está en el SO.
    """
    plat = "mac" if is_mac else "win"
    result = []
    for a in apps:
        if a == OFFICE_PARENT:
            if (any(_is_app_available_on_platform(s, plat) for s in OFFICE_APPS)
                    or any(_is_app_available_on_platform(s, plat) for s in OFFICE_CORE_APPS)):
                result.append(a)
            continue
        if a in COMBO_TOOLS:
            if any(_is_app_available_on_platform(part, plat) for part in COMBO_TOOLS[a]):
                result.append(a)
            continue
        if _is_app_available_on_platform(a, plat):
            result.append(a)
    return result


def metodos_compatibles(adobe_apps: list) -> list:
    """Métodos de Adobe que cubren TODAS las apps elegidas (no se combinan).

    activation_tool queda fuera (no descarga apps individuales).
    """
    methods = [m for m in ADOBE_METHODS if m != "activation_tool"]
    return [
        m for m in methods
        if all(a in _adobe_apps_supported_by_method(m) for a in adobe_apps)
    ]


def preseleccionar_metodo(adobe_apps: list):
    """(compatibles, preseleccionado): aio_macked si es compatible; si no,
    el único/primero compatible."""
    compatible = metodos_compatibles(adobe_apps)
    if len(compatible) == 1:
        return compatible, compatible[0]
    if "aio_macked" in compatible:
        return compatible, "aio_macked"
    return compatible, compatible[0] if compatible else None


def cobertura_metodo(method: str, adobe_apps: list) -> int:
    """Cuántas de las apps Adobe elegidas soporta el método."""
    if not adobe_apps:
        return 0
    return sum(1 for a in adobe_apps if a in _adobe_apps_supported_by_method(method))


def versiones_metodo(method: str, adobe_apps: list) -> list:
    """Versiones concretas disponibles del método para cada app elegida,
    en formato 'App: vX' (solo las apps que el método cubre)."""
    from catalog.adobe_helpers import _adobe_best_link
    out = []
    for app in adobe_apps:
        _url, version = _adobe_best_link(method, app)
        if version:
            out.append(f"{app}: v{version}")
    return out


def clarify_mentions(text: str, apps: list) -> str:
    """Si el texto menciona una app Adobe que NO está seleccionada, lo
    aclara (ej. bullet de Photoshop con Photoshop no elegido)."""
    text = text or ""
    for app in ADOBE_APPS:
        if app in text and app not in (apps or []):
            text += f" (solo si elegiste {app})"
    return text


def bypass_pixeldrain_sirve(file_id: str, timeout: int = 8) -> bool:
    """True si algún mirror bypass sirve el archivo (no HTML).

    Usa HEAD (no GET) para no traer el cuerpo del archivo: el chequeo es
    rápido aunque el archivo pese 11 GB.
    """
    from services.resolver_gateway import PIXELDRAIN_BYPASS_HOSTS
    import urllib.request
    for host in PIXELDRAIN_BYPASS_HOSTS:
        try:
            req = urllib.request.Request(
                f"https://{host}/{file_id}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ct = resp.headers.get("content-type", "")
                total = int(resp.headers.get("content-length", 0) or 0)
                if total > 0 and not ct.startswith("text/html"):
                    return True
        except Exception:
            continue
    return False


def necesita_serializar(tasks) -> bool:
    """True si ≥2 tareas caerán a la API directa de pixeldrain (sin bypass).

    Las que se sirven por el CDN bypass no tocan pixeldrain, así que no
    cuentan para el límite de conexiones de cuentas anónimas.
    """
    from services.resolver_gateway import _pixeldrain_file_id
    direct = 0
    for t in tasks:
        fid = _pixeldrain_file_id(getattr(t, "url_or_magnet", ""))
        if fid and not bypass_pixeldrain_sirve(fid):
            direct += 1
    return direct >= 2


# ── Motor: estado + acciones + reglas ─────────────────────────────


class FlujoMotor:
    """Máquina de estados del flujo, agnóstica de presentación."""

    def __init__(self, client_id: str, hwid: str,
                 is_mac: bool = IS_MAC, is_win: bool = IS_WIN,
                 catalogo: dict | None = None):
        self.state = FlujoEstado()
        self.client_id = client_id
        self.hwid = hwid
        self.is_mac = is_mac
        self.is_win = is_win
        # Catálogo de categorías provisto por el servidor (hoja Links).
        # None = catálogo local (SOFTWARE_CATEGORIES).
        self.catalogo = catalogo

    # ── Acciones sobre el estado ──────────────────────────────────
    def elegir_categoria(self, categoria: str):
        self.state.categoria = categoria

    def agregar_apps(self, apps: list) -> tuple:
        """Acumula apps (multi-categoría), dedup, respetando el límite.
        Devuelve (nuevas_agregadas, limite_restante)."""
        nuevas = [a for a in apps if a not in self.state.seleccion]
        restante = max(0, self.state.max_apps - len(self.state.seleccion))
        permitidas = nuevas[:restante]
        self.state.seleccion.extend(permitidas)
        return permitidas, max(0, restante - len(permitidas))

    def set_seleccion(self, apps: list):
        """Reemplaza la selección completa (uso de la UI, que no acumula)."""
        self.state.seleccion = list(apps)

    def puede_agregar(self) -> bool:
        return len(self.state.seleccion) < self.state.max_apps

    def remover_apps(self, apps: list) -> list:
        """Quita apps de la selección acumulada (deseleccionar).

        Al quitar un Adobe patcheado también sale del listado GenP, y al
        quitar la app padre de Office se limpian sus sub-apps.
        Devuelve las apps efectivamente removidas."""
        removidos = [a for a in apps if a in self.state.seleccion]
        if not removidos:
            return []
        self.state.seleccion = [a for a in self.state.seleccion if a not in apps]
        self.state.adobe_patched = [a for a in self.state.adobe_patched if a not in apps]
        if OFFICE_PARENT in apps:
            self.state.office_sub = []
        return removidos

    def elegir_office(self, sub_apps: list):
        self.state.office_sub = list(sub_apps)

    def marcar_adobe_patched(self, apps: list):
        self.state.adobe_patched = [a for a in apps if a in ADOBE_APPS]

    def elegir_metodo_adobe(self, method: str):
        self.state.adobe_method = method

    def set_limite(self, max_apps: int):
        if max_apps:
            self.state.max_apps = max(1, min(int(max_apps), MAX_APPS))

    def set_activacion(self, activado: bool, max_apps: int, tipo: str):
        self.state.activado = activado
        if max_apps:
            self.state.max_apps = max(1, min(max_apps, MAX_APPS))
        self.state.tipo = tipo

    def en_etapa(self, etapa: Etapa):
        """La vista informa en qué etapa del flujo está."""
        self.state.etapa = etapa

    # ── Reglas de consulta ────────────────────────────────────────
    @property
    def apps_actuales(self) -> list:
        """Apps visibles de la categoría actual para la plataforma."""
        from catalog.data import SOFTWARE_CATEGORIES
        if not self.state.categoria:
            return []
        src = self.catalogo or SOFTWARE_CATEGORIES
        return platform_apps(
            src.get(self.state.categoria, {}).get("apps", []),
            self.is_mac, self.is_win,
        )

    @property
    def ocultas(self) -> list:
        from catalog.data import SOFTWARE_CATEGORIES
        src = self.catalogo or SOFTWARE_CATEGORIES
        all_apps = src.get(self.state.categoria, {}).get("apps", [])
        return [a for a in all_apps if a not in self.apps_actuales]

    def pregunta_adobe_pendiente(self) -> bool:
        """La pregunta GenP solo aplica en Windows y si hay Adobe elegido."""
        if not self.is_win:
            return False
        return any(a in ADOBE_APPS for a in self.state.seleccion)

    @property
    def adobe_seleccionados(self) -> list:
        return [a for a in self.state.seleccion if a in ADOBE_APPS]

    @property
    def adobe_a_descargar(self) -> list:
        return [a for a in self.adobe_seleccionados
                if a not in self.state.adobe_patched]

    def necesita_metodo_adobe(self) -> bool:
        return self.is_mac and bool(self.adobe_a_descargar)

    def efectivo_conteo(self) -> int:
        """Conteo efectivo para el límite (crédito Adobe: N apps cuentan como 1)."""
        non_tool = [a for a in self.state.seleccion if a != OFFICE_PARENT]
        adobe_credit = _adobe_count_for_limit(non_tool)
        non_adobe = [a for a in non_tool if a not in ADOBE_APPS]
        return len(non_adobe) + adobe_credit

    def dentro_del_limite(self) -> bool:
        return self.efectivo_conteo() <= self.state.max_apps

    def tiene_descargable(self, sheet_methods: dict | None = None) -> bool:
        return has_downloadable(self.state.seleccion, self.state.tipo, sheet_methods)

    @property
    def es_full_pack(self) -> bool:
        return self.state.tipo == "adobe_full_pack" and self.is_mac

    def efectos_necesarios(self, sheet_methods: dict | None = None) -> list:
        """Efectos requeridos tras confirmar la selección (el motor decide).

        La vista implementa `Efectos` y ejecuta cada nombre a su manera.
        Sin nada descargable solo se reporta el cierre.
        """
        efectos = []
        if self.tiene_descargable(sheet_methods):
            efectos.append("instrucciones")
            efectos.append("descargar")
            if self.is_win:
                efectos.append("whitelist")
        efectos.append("reportar")
        return efectos

    # ── Transiciones de etapa (máquina de estados) ────────────────
    def siguiente(self) -> Etapa:
        """Decide la próxima etapa según el estado actual (misma lógica
        que _next_seleccion/_next_office/_next_adobe_method de la UI)."""
        cur = self.state.etapa
        if cur == Etapa.SELECCION or cur == Etapa.OFFICE:
            if self.es_full_pack:
                return Etapa.ADOBE_FULLPACK
            if cur == Etapa.SELECCION and OFFICE_PARENT in self.state.seleccion:
                return Etapa.OFFICE
            if self.necesita_metodo_adobe():
                return Etapa.ADOBE_METHOD
            return Etapa.RESUMEN
        if cur == Etapa.ADOBE_METHOD:
            return Etapa.RESUMEN
        if cur == Etapa.ADOBE_FULLPACK:
            return Etapa.RESUMEN
        return Etapa.RESUMEN
