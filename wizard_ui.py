#!/usr/bin/env python3
"""Helpers de terminal y constantes de color del wizard.

Extraído de syops_wizard.py (regla ~900 líneas/archivo). Sin estado de la
aplicación: solo presentación de consola. Los nombres se re-exportan desde
syops_wizard (los tests acceden vía el módulo).
"""

import os
import re
import sys

from catalog.base import IS_MAC, IS_WIN
from catalog.data import ADOBE_APPS

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


def _flush_pending_input():
    """Descarta teclas/Enter que el usuario haya presionado mientras el
    wizard estaba bloqueado esperando una respuesta de red (activación,
    backend, actualización). Si no se descartan, ese input queda en el
    buffer de la terminal y el próximo prompt lo lee como si fuera la
    respuesta, desincronizando el flujo (códigos que caen en prompts
    equivocados, categorías que se responden solas, etc.).
    """
    try:
        if sys.platform == "win32":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        else:
            import select as _sel
            if sys.stdin.isatty():
                fd = sys.stdin.fileno()
            elif _stdin_is_pipe():
                fd = os.open("/dev/tty", os.O_RDONLY)
            else:
                return
            try:
                while _sel.select([fd], [], [], 0)[0]:
                    os.read(fd, 4096)
            finally:
                if fd != sys.stdin.fileno():
                    os.close(fd)
    except Exception:
        pass


# ── Proveedor de input intercambiable (UI web) ───────────────────
# Cuando se setea, _readline() le pide la próxima línea a ESTA callable en
# vez de a la terminal. Lo usa server/web_ui.py para que el mismo Wizard
# (terminal) sea manejado desde el navegador. La terminal queda intacta:
# sin proveedor, _readline lee de stdin como siempre.
_INPUT_PROVIDER = None


def _readline():
    """Lee una línea del teclado.

    Si hay un proveedor de input externo (UI web), se le pide la línea a él.
    Si no, se lee del stdin/terminal (comportamiento original)."""
    if _INPUT_PROVIDER is not None:
        line = _INPUT_PROVIDER()
        if line == "":
            raise EOFError
        return line
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
    _flush_pending_input()
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


def _list_apps(apps, already=None, methods=None):
    already = already or []
    for i, app in enumerate(apps, 1):
        method = _method_label(app, methods)
        mark = _c(" ✓ ya elegido", _GR) if app in already else ""
        print(f"  {_c(str(i).rjust(2), _CY)}. {app:<28} {_c(method, _D)}{mark}")


def _method_label(app, methods=None):
    if app in ADOBE_APPS:
        return "Adobe (método a elegir)"
    m = (methods or {}).get(app)
    if m:
        return m
    from catalog.data import DOWNLOAD_METHODS
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
    """Delega en el esqueleto (app_flow) — la regla vive en app_flow.

    Lee IS_MAC/IS_WIN del módulo syops_wizard en runtime (lazy, evita el
    import circular): los tests parchean syops_wizard.IS_* y la plataforma
    debe tomar el valor vigente.
    """
    from app_flow import platform_apps as _fa
    import syops_wizard as _wiz
    return _fa(apps, _wiz.IS_MAC, _wiz.IS_WIN)


def _pick_adobe_method(adobe_apps):
    """Delega en el esqueleto (app_flow) — la regla vive en app_flow."""
    from app_flow import preseleccionar_metodo
    compatible, default = preseleccionar_metodo(adobe_apps)
    return compatible, default
