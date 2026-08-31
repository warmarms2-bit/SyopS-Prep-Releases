#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  AKIRABOX RESOLVER WORKER
#  Proceso hijo que resuelve una URL de AkiraBox usando QWebEngineView.
#  Corre con su propio QApplication.exec() nativo, porque el motor de
#  QtWebEngine necesita el loop principal para comunicarse con el proceso
#  de renderizado.
#  Se invoca desde la app principal con el flag --akirabox-worker <url>.
# ═══════════════════════════════════════════════════════════════════

import os
import sys
import re
import argparse
from PySide6 import __version__ as PYSIDE6_VERSION
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


# Silenciar logs internos de Chromium y desactivar WebRTC (evita ruido
# de STUN) en la consola del worker.
_extra_flags = "--disable-logging --disable-webrtc --disable-features=WebRTC"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + _extra_flags
).strip()


def _normalize_user_agent(profile):
    """Mantiene el user-agent original de QtWebEngine. En la app bundle el
    ejecutable se anuncia con su nombre propio, lo que algunas protecciones
    de Cloudflare rechazan; restauramos el token QtWebEngine para que sea
    idéntico al de una ejecución desde el intérprete."""
    ua = profile.httpUserAgent()
    if "QtWebEngine/" in ua:
        return ua
    normalized = re.sub(
        r"(Gecko\)) [^ ]+",
        f"\\1 QtWebEngine/{PYSIDE6_VERSION}",
        ua,
    )
    profile.setHttpUserAgent(normalized)
    return normalized


class AkiraboxWorkerPage(QWebEnginePage):
    def __init__(self, profile=None, parent=None):
        super().__init__(profile, parent)
        self._resolved = False

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Silenciar ruido de la consola de la página web.
        pass

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):
        # Usar la versión codificada de la URL para evitar espacios y caracteres
        # especiales en el path, que urllib no acepta directamente.
        s = url.toString(QUrl.FullyEncoded)
        if "/uploads/users/" in s:
            if not self._resolved:
                self._resolved = True
                print(f"AKIRABOX_URL:{s}", flush=True)
                QTimer.singleShot(0, QApplication.instance().quit)
            return False
        return super().acceptNavigationRequest(url, nav_type, isMainFrame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--akirabox-worker", dest="url", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    app = QApplication(sys.argv)

    _normalize_user_agent(QWebEngineProfile.defaultProfile())
    print(f"[AkiraBox worker] iniciando {args.url} (timeout={args.timeout}s)", flush=True)

    view = QWebEngineView()
    view.setWindowTitle("SyopS Prep - AkiraBox")
    view.resize(900, 650)
    view.show()

    page = AkiraboxWorkerPage(view)
    view.setPage(page)

    resolved = False

    def extract_and_click(attempt=1):
        if resolved or page._resolved:
            return
        js = """
            (function(){
                const btn = document.getElementById('download-button');
                if (btn) {
                    const href = btn.href || '';
                    try { btn.click(); } catch(e) {}
                    return {href: href, clicked: true};
                }
                const links = Array.from(document.querySelectorAll('a'));
                for (const a of links) {
                    if (a.href && a.href.includes('/download/')) {
                        try { a.click(); } catch(e) {}
                        return {href: a.href, clicked: true};
                    }
                }
                return null;
            })()
        """
        def cb(result):
            nonlocal resolved
            if resolved or page._resolved:
                return
            if result and result.get("href"):
                view.setWindowTitle("SyopS Prep - Obteniendo enlace directo...")
                page.load(QUrl(result["href"]))
            elif attempt < 20:
                view.setWindowTitle(f"SyopS Prep - Esperando botón de descarga ({attempt})...")
                QTimer.singleShot(2000, lambda: extract_and_click(attempt + 1))
            else:
                view.setWindowTitle("SyopS Prep - Hacé click en el botón de descarga")
        page.runJavaScript(js, cb)

    def on_load_finished(ok):
        QTimer.singleShot(2000, extract_and_click)

    page.loadFinished.connect(on_load_finished)
    page.load(QUrl(args.url))

    QTimer.singleShot(args.timeout * 1000, lambda: (print("AKIRABOX_ERROR:timeout", flush=True), app.quit()))
    app.exec()


if __name__ == "__main__":
    main()
