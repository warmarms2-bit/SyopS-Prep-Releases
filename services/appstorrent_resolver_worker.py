#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  APPSTORENT RESOLVER WORKER
#  Proceso hijo que resuelve una URL de appstorrent.ru usando QWebEngineView.
#  Mismo patrón que akirabox_resolver_worker.py.
#
#  appstorrent está detrás de Cloudflare. El challenge a veces se resuelve
#  automáticamente (JS) y a veces requiere interacción. Este worker:
#   1. Muestra la ventana (el usuario resuelve el captcha si aparece).
#   2. Espera a que el challenge pase (el título deja de ser "Just a moment...").
#   3. Captura la descarga real vía downloadRequested o la navegación a un
#      archivo (uploads/...pkg|dmg|zip).
#
#  Se invoca con --appstorrent-worker <url>.
# ═══════════════════════════════════════════════════════════════════

import os
import sys
import re
import argparse
from PySide6 import __version__ as PYSIDE6_VERSION
from PySide6.QtCore import QTimer, QUrl, Qt  # noqa: F401  (Qt usado por PySide6 en señales)
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
# QWebEngineDownloadRequest se importa porque PySide6 lo necesita en el
# namespace para construir el parámetro del slot de downloadRequested
# (falso positivo de ruff: el tipo se usa implícitamente en la señal).
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest  # noqa: F401


# Silenciar logs internos de Chromium y desactivar WebRTC.
_extra_flags = "--disable-logging --disable-webrtc --disable-features=WebRTC"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + _extra_flags
).strip()

_DOWNLOAD_EXTS = (".pkg", ".dmg", ".zip", ".rar", ".7z", ".exe")


def _normalize_user_agent(profile):
    """Mantiene el user-agent original de QtWebEngine (idéntico al del
    intérprete), que Cloudflare acepta mejor que el de la app bundle."""
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


def _looks_like_download(url: str, original: str = "") -> bool:
    u = (url or "").lower()
    if original and u == original.lower():
        return False
    if ("/uploads/" in u or "/files/" in u or "/download/" in u
            or "/dl/" in u or "/engine/download.php" in u
            or "/download.php" in u):
        return True
    return u.endswith(_DOWNLOAD_EXTS)


class AppstorrentWorkerPage(QWebEnginePage):
    def __init__(self, profile=None, parent=None, original_url=""):
        super().__init__(profile, parent)
        self._resolved = False
        self._original = original_url

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        pass

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):
        s = url.toString(QUrl.FullyEncoded)
        if not self._resolved and _looks_like_download(s, self._original):
            self._resolved = True
            print(f"APPSTORENT_URL:{s}", flush=True)
            QTimer.singleShot(0, QApplication.instance().quit)
            return False
        return super().acceptNavigationRequest(url, nav_type, isMainFrame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--appstorrent-worker", dest="url", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    app = QApplication(sys.argv)

    _normalize_user_agent(QWebEngineProfile.defaultProfile())
    print(f"[Appstorrent worker] iniciando {args.url} (timeout={args.timeout}s)", flush=True)
    print("[Appstorrent worker] Si aparece el captcha de Cloudflare, resolvelo.", flush=True)

    view = QWebEngineView()
    view.setWindowTitle("SyopS Prep - Appstorrent")
    view.resize(900, 650)
    view.show()

    page = AppstorrentWorkerPage(view, original_url=args.url)
    view.setPage(page)

    captured = {"url": ""}

    # Capturar descargas iniciadas por el navegador.
    def on_download_requested(download):
        url = download.url().toString()
        if not captured["url"] and _looks_like_download(url, args.url):
            captured["url"] = url
            print(f"APPSTORENT_URL:{url}", flush=True)
            QTimer.singleShot(0, app.quit)
        download.cancel()

    QWebEngineProfile.defaultProfile().downloadRequested.connect(on_download_requested)

    def poll_download(attempt=1):
        """Busca el botón/enlace de descarga real y lo clica."""
        if page._resolved or captured["url"]:
            return
        js = """
            (function(){
                const ORIG = %r;
                const cands = Array.from(document.querySelectorAll('a, button'));
                for (const el of cands) {
                    const href = el.href || el.getAttribute('href') || '';
                    const txt = (el.innerText || '').toLowerCase();
                    const isDl = new RegExp("download|/uploads/|/files/|/dl/|\\.pkg(?:$|[?#])|\\.dmg(?:$|[?#])|\\.zip(?:$|[?#])|скачать", "i").test(href + ' ' + txt);
                    if (isDl && !href.startsWith('javascript:')
                        && (!href || href !== ORIG)) {
                        try { el.click(); } catch(e) {}
                        return {href: href};
                    }
                }
                return null;
            })()
        """ % (args.url,)
        def cb(result):
            if page._resolved or captured["url"]:
                return
            if result and result.get("href"):
                view.setWindowTitle("SyopS Prep - Obteniendo enlace...")
                page.load(QUrl(result["href"]))
            elif attempt < 40:
                view.setWindowTitle(f"SyopS Prep - Esperando descarga ({attempt})...")
                QTimer.singleShot(2000, lambda: poll_download(attempt + 1))
        page.runJavaScript(js, cb)

    def check_state(attempt=1):
        """Monitorea el título: cuando deja de ser 'Just a moment...',
        el challenge pasó; buscar el enlace de descarga."""
        if page._resolved or captured["url"]:
            return
        def title_cb(title):
            if page._resolved or captured["url"]:
                return
            if title != "Just a moment...":
                view.setWindowTitle(f"SyopS Prep - {title[:40]}")
                poll_download()
            if attempt < 90:
                QTimer.singleShot(2000, lambda: check_state(attempt + 1))
        page.runJavaScript("document.title", title_cb)

    page.load(QUrl(args.url))
    QTimer.singleShot(1500, check_state)

    QTimer.singleShot(args.timeout * 1000, lambda: (print("APPSTORENT_ERROR:timeout", flush=True), app.quit()))
    app.exec()


if __name__ == "__main__":
    main()
