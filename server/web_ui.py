"""SyopS Prep — UI web local que maneja el MISMO Wizard de terminal.

El wizard (syops_wizard.Wizard) corre en un hilo con:
  - input: wizard_ui._INPUT_PROVIDER → cola alimentada por el navegador
  - output: stdout redirigido a un buffer compartido

La terminal sigue intacta: el proveedor SOLO se setea al usar la web.

Ejecutar:
    python3 server/web_ui.py          # abre http://127.0.0.1:8899
    SYOPS_WEB_PORT=8899 python3 server/web_ui.py --no-open
"""

import contextlib
import io
import json
import os
import queue
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PORT = int(os.environ.get("SYOPS_WEB_PORT", "8899"))

# El wizard vive en la raíz del repo; al correr `python3 server/web_ui.py`
# sys.path[0] es server/, así que agregamos la raíz explícitamente.
sys.path.insert(0, str(ROOT))

input_q: queue.Queue = queue.Queue()
output_buf: list = []
output_lock = threading.Lock()
state = {"page": "inicio", "waiting_input": False, "finished": False,
         "error": None}
state_lock = threading.Lock()
waiting_evt = threading.Event()
_started = False
_wizard = None
_gen = 0


class _Aborted(Exception):
    pass


class _Capture(io.TextIOBase):
    """Captura lo que el wizard imprime (stdout) hacia el buffer web."""

    def write(self, s: str) -> int:
        with output_lock:
            output_buf.append(s)
        return len(s)

    def flush(self) -> None:
        pass


def _make_input_provider(gen: int):
    """Crea el provider de input de UNA generación del wizard.

    Cada generación tiene su propio provider con su ``gen``. Un sentinel de
    abort se consume SOLO si pertenece a la generación actual (si no, se
    ignora y se sigue esperando): así un ``REINICIAR`` no deja el input de
    otra generación colgado en la cola."""
    def _prov() -> str:
        waiting_evt.set()
        with state_lock:
            state["waiting_input"] = True
        try:
            while True:
                ans = input_q.get(timeout=3600)
                if isinstance(ans, str) and ans.startswith("__ABORT__:"):
                    # El sentinel lleva la generación a abortar. Se debe
                    # comparar contra la gen PROPIA de este provider (clausura),
                    # NO contra el _gen global: tras un REINICIAR el global ya
                    # apunta a la generación nueva, así que el hilo viejo nunca
                    # abortaba y seguía consumiendo input (reimprimía el menú).
                    try:
                        target = int(ans.split("__ABORT__:", 1)[1])
                    except ValueError:
                        continue
                    if target == gen:
                        raise _Aborted()
                    continue  # sentinel de otra generación -> ignorar
                return str(ans) + "\n"
        except queue.Empty:
            raise EOFError
        finally:
            waiting_evt.clear()
            with state_lock:
                state["waiting_input"] = False
    return _prov

def run_wizard(gen: int) -> None:
    try:
        import wizard_ui
        wizard_ui._INPUT_PROVIDER = _make_input_provider(gen)
        wizard_ui._COLOR_OK = False  # la salida web no debe llevar ANSI
    except Exception as exc:  # noqa: BLE001
        with state_lock:
            state["error"] = f"{type(exc).__name__}: {exc}"
            state["finished"] = True
        return
    try:
        global _wizard
        from syops_wizard import Wizard
        _wizard = Wizard()
        with contextlib.redirect_stdout(_Capture()):
            _wizard.run()
    except (_Aborted, SystemExit):
        pass  # WizardCancelled / fin del wizard / reinicio
    except Exception as exc:  # noqa: BLE001
        if gen == _gen:
            with state_lock:
                state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if gen == _gen:
            with state_lock:
                state["finished"] = True
            wizard_ui._INPUT_PROVIDER = None


def start() -> bool:
    global _started, _gen
    if _started:
        return False
    _gen += 1
    _started = True
    threading.Thread(target=run_wizard, args=(_gen,), daemon=True).start()
    return True


def restart() -> bool:
    """Reinicia el flujo desde el paso 1 (aborta el hilo anterior y arranca
    uno nuevo). Se usa para corregir errores sin cerrar el navegador."""
    global _gen, _started
    old_gen = _gen
    _gen += 1
    input_q.put(f"__ABORT__:{old_gen}")          # desbloquea el provider del hilo viejo
    with output_lock:
        output_buf.clear()
    with state_lock:
        state.update({"page": "inicio", "waiting_input": False,
                      "finished": False, "error": None})
    _started = True
    threading.Thread(target=run_wizard, args=(_gen,), daemon=True).start()
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencio
        pass

    def _send(self, code: int, body, ctype: str = "application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, (WEB / "index.html").read_text(encoding="utf-8"),
                       "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            f = WEB / path[len("/static/"):]
            if f.is_file():
                ctype = {
                    ".css": "text/css", ".js": "text/javascript",
                    ".png": "image/png", ".ttf": "font/ttf",
                    ".otf": "font/otf", ".woff2": "font/woff2",
                    ".wav": "audio/wav", ".mp3": "audio/mpeg",
                }.get(f.suffix, "application/octet-stream")
                self._send(200, f.read_bytes(), ctype)
                return
            self._send(404, "not found")
            return
        if path == "/api/start":
            start()
            self._send(200, json.dumps({"ok": True}))
            return
        if path == "/api/restart":
            restart()
            self._send(200, json.dumps({"ok": True}))
            return
        if path == "/api/state":
            # El buffer se devuelve SIEMPRE completo (idempotente): el cliente
            # re-renderiza el estado exacto del wizard. Así se evita que un
            # delta/offset mal sincronizado duplique o borre contenido en el
            # navegador (bug "aparece dos veces el menú").
            with output_lock:
                out = "".join(output_buf)
                offset = len(output_buf)
            with state_lock:
                st = dict(state)
            if _wizard is not None:
                st["page"] = getattr(_wizard, "current_page", st["page"])
            st["output"] = out
            st["offset"] = offset
            # working = procesando entre prompts (para el spinner de la UI)
            st["working"] = (not st["waiting_input"]) and (not st["finished"]) and (not st["error"])
            self._send(200, json.dumps(st, ensure_ascii=False))
            return
        self._send(404, "not found")

    def do_POST(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/start":
            start()
            self._send(200, json.dumps({"ok": True}))
            return
        if path == "/api/restart":
            restart()
            self._send(200, json.dumps({"ok": True}))
            return
        if path == "/api/input":
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                data = {}
            input_q.put(str(data.get("answer", "")))
            self._send(200, json.dumps({"ok": True}))
            return
        self._send(404, "not found")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="UI web del wizard (usa el mismo Wizard)")
    ap.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    ap.add_argument("--demo", action="store_true",
                    help="modo demo: saltea activación y simula descargas (solo pruebas)")
    args = ap.parse_args()
    if args.demo:
        os.environ["SYOPS_DEMO"] = "1"
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"SyopS Prep UI: {url}  (Ctrl+C para salir)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nAdiós.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
