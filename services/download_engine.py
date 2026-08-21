#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  DOWNLOAD ENGINE - Motor de descargas HTTP (Surge) y Torrent
#  Extraido de syops_prep.py para mantener el archivo principal
#  enfocado en la interfaz y el flujo de la aplicación.
# ═══════════════════════════════════════════════════════════════════

import asyncio
import subprocess
import json
import re
import urllib.request
import urllib.parse
from urllib.parse import unquote
import threading
import concurrent.futures
from pathlib import Path
from datetime import datetime

from services.signals import Signal

from i18n import _
from services.download_config import HTTP_TIMEOUT, SEGMENT_CHUNK, SEGMENTED_MIN_SIZE, SEGMENTED_SEGMENTS
from services.http_utils import (
    _safe_eta,
    _safe_pct,
    _format_eta,
    _download_segment,
    _verify_file_sha256,
    _filename_from_content_disposition,
    _guess_extension_from_url,
    validate_downloaded_file,
)
from services.resolver_gateway import (
    _pixeldrain_file_id,
    _pixeldrain_file_info,
    _resolve_pixeldrain_download_url,
    pixeldrain_resolved_metadata,
    TorrentDownloader,
)
import logging

logger = logging.getLogger(__name__)

from syops_utils import app_dir, log_error, _NOWINDOW


def _http_headers(url: str) -> dict:
    """Headers de navegador real para evitar bloqueos de CDNs/protecciones."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
    }
    if "akirabox." in url.lower():
        headers["Referer"] = "https://akirabox.to/"
    return headers


def _clean_cd_name(cd_name: str) -> str:
    if not cd_name:
        return cd_name
    cd_name = unquote(cd_name)
    return cd_name.replace("/", "_").replace("\\", "_")


# ── DownloadEngine: gestiona descargas HTTP (Surge) y Torrent ─────
class DownloadEngine(TorrentDownloader):
    # name, pct, status_text, downloaded_bytes, total_bytes
    # NOTA: los ultimos dos parametros usan qint64 (64 bits) porque los
    # tamanos de archivo (p.ej. torrents de varios GB) superan INT_MAX de C++
    # y provocarian OverflowError al emitir la senal (con Qt). Con el Signal
    # puro (services/signals.py) no hay limite, se conserva la firma igual.
    progress = Signal(str, int, str, int, int)
    completed = Signal(object, object, object)

    def _emit_progress(self, name: str, pct: int, status: str, downloaded: int, total: int):
        try:
            self.progress.emit(name, int(pct), str(status), int(downloaded), int(total))
        except Exception as e:
            logger.warning("progress.emit failed: %s", e)
            log_error(f"[DownloadEngine] progress.emit failed: {e}")

    def _emit_completed(self, name, success, size):
        try:
            self.completed.emit(name, bool(success), int(size))
        except Exception as e:
            logger.warning("completed.emit failed: %s", e)
            log_error(f"[DownloadEngine] completed.emit failed: {e}")

    def __init__(self):
        super().__init__()
        self.session = None
        self.surge_process = None
        self.surge_started = False
        self.surge_token = "syops_prep"
        self.surge_port = 17890
        self._connection_failed = False

    def _surge_path(self) -> Path:
        return app_dir() / "surge.exe"

    def _check_surge_health(self) -> bool:
        try:
            req = urllib.request.Request(
                f"http://localhost:{self.surge_port}/api/v1/health",
                headers={"Authorization": f"Bearer {self.surge_token}"}
            )
            urllib.request.urlopen(req, timeout=2)
            self.surge_started = True
            return True
        except Exception:
            return False

    async def _start_surge(self):
        if self.surge_started:
            return True
        surge = self._surge_path()
        if not surge.exists():
            return False
        if self._check_surge_health():
            return True
        try:
            self.surge_process = subprocess.Popen(
                [str(surge), "server", "--port", str(self.surge_port),
                 "--token", self.surge_token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NOWINDOW
            )
            for _attempt in range(10):
                await asyncio.sleep(1)
                if self._check_surge_health():
                    return True
        except Exception as e:
            logger.warning("Error starting Surge: %s", e)
        return False

    def _surge_api(self, method: str, path: str, data: dict = None):
        url = f"http://localhost:{self.surge_port}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {self.surge_token}",
                "Content-Type": "application/json"
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode())

    async def download_http(self, name: str, url: str, dest_dir: Path, headers_extra: dict[str, str] | None = None):
        if headers_extra:
            # Surge no soporta headers custom (cookies, tokens, etc.)
            logger.info("[DESCARGA] %s: FALLBACK+HEADERS | url=%s", name, url[:60])
            await self._download_http_with_headers(name, url, dest_dir, headers_extra)
            return

        # Detectar Pixeldrain y resolver bypass ANTES de Surge
        is_pixeldrain = bool(_pixeldrain_file_id(url))
        resolved_url = None
        bypass_mirror = None
        
        if is_pixeldrain:
            # Resolver bypass primero para evitar límite de 6GB/día
            resolved_result = await asyncio.to_thread(_resolve_pixeldrain_download_url, url)
            resolved_url, total, supports_range, cd_name = resolved_result
            if resolved_url:
                # Determinar qué mirror se usó
                if "isuru.eu.org" in resolved_url:
                    bypass_mirror = "isuru.eu.org"
                elif "gamedrive.org" in resolved_url:
                    bypass_mirror = "gamedrive.org"
                else:
                    bypass_mirror = "API directa"

        surge_ok = await self._start_surge()
        if surge_ok:
            try:
                # Usar resolved_url si es Pixeldrain, sino url original
                surge_url = resolved_url if resolved_url else url
                path_taken = "SURGE+BYPASS" if (is_pixeldrain and resolved_url) else "SURGE"
                logger.info("[DESCARGA] %s: %s | mirror=%s | url=%s", name, path_taken, bypass_mirror or "N/A", surge_url[:60])
                
                self._emit_progress(name, 0, _("descarga.status_surge"), 0, 0)
                result = self._surge_api("POST", "/api/v1/downloads", {
                    "urls": [surge_url],
                    "outputDir": str(dest_dir)
                })
                dl_id = result.get("id", "")
                if not dl_id:
                    downloads = result.get("downloads") or []
                    if downloads:
                        dl_id = downloads[0].get("id", "")
                no_progress = 0
                last_downloaded = 0
                api_errors = 0
                while True:
                    await asyncio.sleep(1)
                    try:
                        status = self._surge_api("GET", f"/api/v1/downloads/{dl_id}")
                        dl = status if "progress" in status else status.get("downloads", [status])[0]
                        raw_progress = dl.get("progress", 0)
                        try:
                            pct = int(float(raw_progress) * 100)
                        except Exception:
                            pct = 0
                        speed = dl.get("speed", 0)
                        total = dl.get("totalSize", 0)
                        downloaded = dl.get("downloaded", 0)
                        try:
                            speed_mb = float(speed) / (1024 * 1024) if speed else 0
                        except Exception:
                            speed_mb = 0
                        api_errors = 0
                        if downloaded == last_downloaded:
                            no_progress += 1
                        else:
                            no_progress = 0
                            last_downloaded = downloaded
                        if no_progress > 240:
                            self._emit_progress(name, pct, _("descarga.status_sin_conexion"), downloaded, total)
                            self._emit_completed(name, False, 0)
                            self._connection_failed = True
                            return
                        if total > 0:
                            remaining = total - downloaded
                            if speed_mb > 0:
                                eta_sec = _safe_eta(remaining / (speed_mb * 1024 * 1024))
                                eta_str = _format_eta(eta_sec)
                            else:
                                eta_str = _("descarga.status_calculando")
                            self._emit_progress(name, pct,
                                f"{downloaded // (1024*1024)}MB / {total // (1024*1024)}MB - {speed_mb:.1f} MB/s | ETA: {eta_str}", downloaded, total)
                        else:
                            self._emit_progress(name, pct, f"{speed_mb:.1f} MB/s", downloaded, total)
                        dl_status = dl.get("status", "")
                        if dl_status == "completed":
                            break
                        if dl_status in ("failed", "error"):
                            raise Exception("Surge download failed")
                        if total > 0 and downloaded >= total:
                            break
                    except Exception as e:
                        if "Surge download failed" in str(e):
                            raise
                        api_errors += 1
                        if api_errors > 30:
                            self._emit_progress(name, 0, _("descarga.status_error_surge"), 0, 0)
                            self._emit_completed(name, False, 0)
                            return
                self._emit_completed(name, True, downloaded)
                return
            except Exception as e:
                logger.warning("Error Surge %s: %s", name, e)
        
        # Fallback: si es Pixeldrain y ya tenemos resolved_url, usarlo directamente
        if is_pixeldrain and resolved_url:
            logger.info("[DESCARGA] %s: FALLBACK+BYPASS | mirror=%s | url=%s", name, bypass_mirror, resolved_url[:60])
            await self._download_http_pixeldrain(name, url, dest_dir, resolved_url=resolved_url)
        else:
            logger.info("[DESCARGA] %s: FALLBACK | url=%s", name, url[:60])
            await self._download_http_fallback(name, url, dest_dir)

    async def _download_http_with_headers(self, name: str, url: str, dest_dir: Path, headers_extra: dict[str, str]):
        """Descarga HTTP directa con headers custom (cookies, tokens, etc.).
        Salta Surge porque no soporta headers personalizados."""
        ext = _guess_extension_from_url(url)
        safe_name = name.replace(" ", "_")
        if not safe_name.lower().endswith(ext.lower()):
            safe_name = f"{safe_name}{ext}"
        dest = dest_dir / safe_name
        temp = dest.with_suffix(".tmp")
        try:
            self._emit_progress(name, 0, _("descarga.status_descargando"), 0, 0)
            await asyncio.to_thread(
                self._download_with_headers_sync, name, url, headers_extra, dest, temp, dest_dir
            )
        except Exception as e:
            logger.warning("Error %s: %s", name, e)
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            self._emit_completed(name, False, 0)

    def _read_loop(self, name, response, f, total, start_bytes=0):
        """Loop de lectura + emisión de progreso compartido por todos los
        descargadores síncronos (fallback, headers, single). Evita duplicar
        el cálculo de velocidad/ETA en cada ruta. Devuelve (downloaded, total)."""
        downloaded = start_bytes
        last_time = datetime.now().timestamp()
        last_bytes = start_bytes
        while True:
            chunk = response.read(SEGMENT_CHUNK)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            now = datetime.now().timestamp()
            elapsed = now - last_time
            if elapsed >= 1:
                speed = (downloaded - last_bytes) / elapsed / (1024 * 1024)
                last_bytes = downloaded
                last_time = now
                if total > 0:
                    pct = _safe_pct((downloaded / total) * 100)
                    remaining = total - downloaded
                    eta_sec = _safe_eta(remaining / (speed * 1024 * 1024)) if speed > 0 else 0
                    eta_str = _format_eta(eta_sec)
                    self._emit_progress(name, pct,
                        f"{downloaded // (1024*1024)}MB / {total // (1024*1024)}MB - {speed:.1f} MB/s | ETA: {eta_str}", downloaded, total)
                else:
                    self._emit_progress(name, 0, f"{downloaded // (1024*1024)}MB - {speed:.1f} MB/s", downloaded, total)
        return downloaded, total

    def _download_with_headers_sync(self, name, url, headers_extra, dest, temp, dest_dir):
        """Sincrona: descarga con headers custom, misma señales que _fallback_download_sync."""
        headers = _http_headers(url)
        headers.update(headers_extra)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            try:
                total = int(response.headers.get("content-length", 0))
            except Exception:
                total = 0
            cd_name = _clean_cd_name(
                _filename_from_content_disposition(response.headers.get("content-disposition", ""))
            )
            if cd_name:
                dest = dest_dir / cd_name
                temp = dest.with_suffix(".tmp")
            with open(temp, "wb") as f:
                downloaded, total = self._read_loop(name, response, f, total)
        if dest.exists():
            dest.unlink()
        temp.rename(dest)
        if not validate_downloaded_file(dest, total):
            raise Exception("Archivo descargado inválido (HTML o tamaño incorrecto)")
        self._emit_completed(name, True, downloaded)

    async def _download_http_fallback(self, name: str, url: str, dest_dir: Path):
        is_pixeldrain = bool(_pixeldrain_file_id(url))
        if is_pixeldrain:
            await self._download_http_pixeldrain(name, url, dest_dir)
            return

        # Aceleración genérica: si el host responde Accept-Ranges y el archivo
        # es grande, descargar en N segmentos paralelos en vez de un hilo solo.
        supports_range, total = await asyncio.to_thread(self._probe_range_sync, url)
        if supports_range and total >= SEGMENTED_MIN_SIZE:
            ok = await self._download_http_segmented(name, url, dest_dir, total)
            if ok is not None:
                return

        ext = _guess_extension_from_url(url)
        safe_name = name.replace(" ", "_")
        if not safe_name.lower().endswith(ext.lower()):
            safe_name = f"{safe_name}{ext}"
        dest = dest_dir / safe_name
        temp = dest.with_suffix(".tmp")
        try:
            self._emit_progress(name, 0, _("descarga.status_descargando"), 0, 0)
            await asyncio.to_thread(
                self._fallback_download_sync, name, url, dest, temp, dest_dir
            )
        except Exception as e:
            logger.warning("Error %s: %s", name, e)
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            self._emit_completed(name, False, 0)

    def _probe_range_sync(self, url: str) -> tuple:
        """HEAD a una URL: (supports_range, content_length). No trae el cuerpo."""
        try:
            req = urllib.request.Request(url, headers=_http_headers(url), method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as resp:
                supports = resp.headers.get("accept-ranges", "").lower() == "bytes"
                total = int(resp.headers.get("content-length", 0) or 0)
                return supports and total > 0, total
        except Exception:
            return False, 0

    async def _download_http_segmented(self, name: str, url: str, dest_dir: Path,
                                       total: int, num_segments: int = None):
        """Descarga HTTP genérica en N segmentos paralelos (Range).

        Usado para hosts con Accept-Ranges que no son Pixeldrain: acelera
        descargas grandes con varias conexiones al mismo servidor.
        Devuelve None si no correspondía segmentar (para volver al single).
        """
        if num_segments is None:
            num_segments = SEGMENTED_SEGMENTS
        if total < SEGMENTED_MIN_SIZE:
            return None
        ext = _guess_extension_from_url(url)
        safe_name = name.replace(" ", "_")
        if not safe_name.lower().endswith(ext.lower()):
            safe_name = f"{safe_name}{ext}"
        dest = dest_dir / safe_name
        temp = dest.with_suffix(".tmp")
        try:
            # Reanudación: si el temporal ya está completo, considerar listo.
            if temp.exists() and temp.stat().st_size == total:
                if validate_downloaded_file(temp, total):
                    if dest.exists():
                        dest.unlink()
                    temp.rename(dest)
                    self._emit_completed(name, True, total)
                    return True

            self._emit_progress(name, 0, _("descarga.status_descargando_segmentos"), 0, total)
            if temp.exists():
                temp.unlink()
            with open(temp, "wb") as f:
                f.truncate(total)

            downloaded = 0
            lock = threading.Lock()
            last_report = [datetime.now().timestamp(), 0]
            stop_event = threading.Event()

            def on_chunk(size):
                nonlocal downloaded
                with lock:
                    downloaded += size
                    now = datetime.now().timestamp()
                    if now - last_report[0] >= 1:
                        speed = (downloaded - last_report[1]) / (now - last_report[0]) / (1024 * 1024)
                        last_report[0] = now
                        last_report[1] = downloaded
                        pct = _safe_pct((downloaded / total) * 100)
                        remaining = total - downloaded
                        eta_sec = _safe_eta(remaining / (speed * 1024 * 1024)) if speed > 0 else 0
                        eta_str = _format_eta(eta_sec)
                        self._emit_progress(name, pct,
                            f"{downloaded // (1024*1024)}MB / {total // (1024*1024)}MB - {speed:.1f} MB/s | ETA: {eta_str}", downloaded, total)

            segment_size = total // num_segments
            ranges = []
            for i in range(num_segments):
                start = i * segment_size
                end = start + segment_size - 1 if i < num_segments - 1 else total - 1
                ranges.append((start, end))

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as executor:
                futures = [loop.run_in_executor(executor, _download_segment, url, start, end, temp, on_chunk, stop_event) for start, end in ranges]
                results = await asyncio.gather(*futures)

            if not all(results):
                raise Exception("Algunos segmentos fallaron")

            if stop_event.is_set():
                raise Exception("Descarga cancelada")

            if not validate_downloaded_file(temp, total):
                raise Exception("Archivo descargado inválido")

            if dest.exists():
                dest.unlink()
            temp.rename(dest)
            self._emit_progress(name, 100,
                f"{total // (1024*1024)}MB / {total // (1024*1024)}MB - 0.0 MB/s | ETA: 0s", total, total)
            self._emit_completed(name, True, total)
            return True
        except Exception as e:
            logger.warning("Error segmentado %s: %s", name, e)
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            # Fallar afuera NO: volvemos None para que el llamador use single.
            return None

    def _fallback_download_sync(self, name, url, dest, temp, dest_dir):
        req = urllib.request.Request(url, headers=_http_headers(url))
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            try:
                total = int(response.headers.get("content-length", 0))
            except Exception:
                total = 0
            cd_name = _clean_cd_name(
                _filename_from_content_disposition(response.headers.get("content-disposition", ""))
            )
            if cd_name:
                dest = dest_dir / cd_name
                temp = dest.with_suffix(".tmp")
            with open(temp, "wb") as f:
                downloaded, total = self._read_loop(name, response, f, total)
        if dest.exists():
            dest.unlink()
        temp.rename(dest)
        if not validate_downloaded_file(dest, total):
            raise Exception("Archivo descargado inválido (HTML o tamaño incorrecto)")
        self._emit_completed(name, True, downloaded)

    async def _download_http_pixeldrain(self, name: str, url: str, dest_dir: Path, num_segments: int = 4, resolved_url: str = None):
        """Descarga archivos de Pixeldrain usando bypass + Range requests.

        1. Intenta resolver por bypass para evitar el límite de 6GB/día.
        2. Si el bypass falla, usa la API directa de Pixeldrain.
        3. Si el servidor final soporta Range, descarga en paralelo por segmentos
           con reintentos y reanudación parcial.
        
        Si resolved_url se pasa, se usa directamente sin volver a resolver.
        """
        max_attempts = 3
        expected_hash = None
        try:
            _info = _pixeldrain_file_info(url)
            if _info:
                expected_hash = _info[2]
        except Exception:
            pass

        for attempt in range(max_attempts):
            try:
                if resolved_url:
                    # Ya tenemos el link resuelto, no volver a resolver
                    self._emit_progress(name, 0, _("descarga.status_resolviendo"), 0, 0)
                    # Obtener metadata del link resuelto (bloqueante → to_thread)
                    total, cd_name, supports_range = await asyncio.to_thread(
                        pixeldrain_resolved_metadata, resolved_url
                    )
                else:
                    # Resolver desde cero
                    self._emit_progress(name, 0, _("descarga.status_resolviendo"), 0, 0)
                    resolved_url, total, supports_range, cd_name = await asyncio.to_thread(
                        _resolve_pixeldrain_download_url, url
                    )
                    if not resolved_url:
                        raise Exception("No se pudo resolver el link de descarga")

                ext = _guess_extension_from_url(resolved_url)
                safe_name = name.replace(" ", "_")
                if not safe_name.lower().endswith(ext.lower()):
                    safe_name = f"{safe_name}{ext}"
                if cd_name:
                    cd_name = cd_name.replace("/", "_").replace("\\", "_")
                    if cd_name:
                        safe_name = cd_name
                dest = dest_dir / safe_name
                temp = dest.with_suffix(".tmp")

                if total <= 0 or not supports_range or total < 10 * 1024 * 1024:
                    await self._download_http_single(name, resolved_url, dest, temp, total, expected_hash)
                    return

                # Reanudación: si el archivo temporal ya existe y tiene el tamaño
                # correcto, considerarlo completo.
                if temp.exists() and temp.stat().st_size == total:
                    if validate_downloaded_file(temp, total):
                        if dest.exists():
                            dest.unlink()
                        temp.rename(dest)
                        self._emit_completed(name, True, total)
                        return

                # Descarga segmentada en paralelo.
                self._emit_progress(name, 0, _("descarga.status_descargando_segmentos"), 0, total)
                if temp.exists():
                    temp.unlink()
                with open(temp, "wb") as f:
                    f.truncate(total)

                downloaded = 0
                lock = threading.Lock()
                last_report = [datetime.now().timestamp(), 0]
                stop_event = threading.Event()

                def on_chunk(size):
                    nonlocal downloaded
                    with lock:
                        downloaded += size
                        now = datetime.now().timestamp()
                        if now - last_report[0] >= 1:
                            speed = (downloaded - last_report[1]) / (now - last_report[0]) / (1024 * 1024)
                            last_report[0] = now
                            last_report[1] = downloaded
                            pct = _safe_pct((downloaded / total) * 100)
                            remaining = total - downloaded
                            eta_sec = _safe_eta(remaining / (speed * 1024 * 1024)) if speed > 0 else 0
                            eta_str = _format_eta(eta_sec)
                            self._emit_progress(name, pct,
                                f"{downloaded // (1024*1024)}MB / {total // (1024*1024)}MB - {speed:.1f} MB/s | ETA: {eta_str}", downloaded, total)

                segment_size = total // num_segments
                ranges = []
                for i in range(num_segments):
                    start = i * segment_size
                    end = start + segment_size - 1 if i < num_segments - 1 else total - 1
                    ranges.append((start, end))

                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as executor:
                    futures = [loop.run_in_executor(executor, _download_segment, resolved_url, start, end, temp, on_chunk, stop_event) for start, end in ranges]
                    results = await asyncio.gather(*futures)

                if not all(results):
                    raise Exception("Algunos segmentos fallaron")

                if stop_event.is_set():
                    raise Exception("Descarga cancelada")

                if not validate_downloaded_file(temp, total):
                    raise Exception("Archivo descargado inválido")
                if expected_hash and not _verify_file_sha256(temp, expected_hash):
                    raise Exception("Hash SHA256 no coincide")

                if dest.exists():
                    dest.unlink()
                temp.rename(dest)
                self._emit_progress(name, 100,
                    f"{total // (1024*1024)}MB / {total // (1024*1024)}MB - 0.0 MB/s | ETA: 0s", total, total)
                self._emit_completed(name, True, total)
                return
            except Exception as e:
                logger.warning("Error Pixeldrain %s (attempt %s/%s): %s", name, attempt + 1, max_attempts, e)
                if attempt < max_attempts - 1:
                    # Forzar re-resolución completa en el retry siguiente
                    resolved_url = None
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    try:
                        temp = dest_dir / (name.replace(" ", "_") + ".tmp")
                        temp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self._emit_completed(name, False, 0)

    async def _download_http_single(self, name: str, url: str, dest: Path, temp: Path, total_hint: int = 0, expected_hash: str = None):
        """Descarga un archivo de una sola vez (sin segmentos) con reanudación."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resume_from = 0
                if temp.exists():
                    resume_from = temp.stat().st_size
                    if total_hint > 0 and resume_from >= total_hint:
                        if dest.exists():
                            dest.unlink()
                        temp.rename(dest)
                        if total_hint > 0 and resume_from != total_hint:
                            logger.warning("WARNING: actual file size (%s) differs from total_hint (%s) for %s",
                                           resume_from, total_hint, name)
                        expected_size = resume_from if total_hint > 0 else 0
                        if not validate_downloaded_file(dest, expected_size):
                            raise Exception("Archivo descargado inválido (HTML o tamaño incorrecto)")
                        self._emit_completed(name, True, resume_from)
                        return

                headers = _http_headers(url)
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"
                    self._emit_progress(name, 0, _("descarga.status_reanudando"), resume_from, total_hint)
                else:
                    self._emit_progress(name, 0, _("descarga.status_descargando"), 0, total_hint)

                result = await asyncio.to_thread(
                    self._single_download_sync, name, url, headers, dest, temp, resume_from, total_hint
                )
                downloaded, total = result

                if total > 0 and downloaded < total:
                    raise Exception(f"Descarga incompleta: {downloaded}/{total}")
                if not validate_downloaded_file(temp, total):
                    raise Exception("Archivo descargado inválido (HTML o tamaño incorrecto)")
                if expected_hash and not _verify_file_sha256(temp, expected_hash):
                    raise Exception("Hash SHA256 no coincide")
                if dest.exists():
                    dest.unlink()
                temp.rename(dest)
                self._emit_completed(name, True, downloaded)
                return
            except Exception as e:
                logger.warning("Error single download %s (attempt %s/%s): %s", name, attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    try:
                        temp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self._emit_completed(name, False, 0)

    def _single_download_sync(self, name, url, headers, dest, temp, resume_from, total_hint):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            try:
                cl = int(response.headers.get("content-length", 0))
            except Exception:
                cl = 0

            if resume_from > 0:
                if response.status == 206:
                    cr = response.headers.get("content-range", "")
                    m = re.search(r"/(\d+)", cr)
                    if m:
                        total = int(m.group(1))
                        if total_hint > 0 and total != total_hint:
                            logger.warning("WARNING: Content-Range total (%s) differs from total_hint (%s) for %s",
                                           total, total_hint, name)
                    else:
                        logger.warning("WARNING: 206 without Content-Range total for %s, falling back to total_hint (%s)",
                                       name, total_hint)
                        total = total_hint
                else:
                    logger.warning("Server responded %s (not 206) to Range request for %s; restarting download from scratch",
                                   response.status, name)
                    resume_from = 0
                    total = cl or total_hint
                    try:
                        temp.unlink(missing_ok=True)
                    except Exception:
                        pass
            else:
                total = cl or total_hint

            cd_name = _clean_cd_name(
                _filename_from_content_disposition(response.headers.get("content-disposition", ""))
            )
            if cd_name:
                dest = dest.parent / cd_name
                temp = dest.with_suffix(".tmp")
            mode = "ab" if resume_from > 0 else "wb"
            with open(temp, mode) as f:
                downloaded, total = self._read_loop(name, response, f, total, start_bytes=resume_from)
        return downloaded, total

    def stop_surge(self):
        if self.surge_process:
            try:
                self.surge_process.terminate()
                self.surge_process.wait(timeout=5)
            except Exception:
                try:
                    self.surge_process.kill()
                    self.surge_process.wait(timeout=3)
                except Exception:
                    pass
            self.surge_process = None
        self.surge_started = False

    def shutdown(self):
        self.stop_surge()
        if self.session:
            try:
                self.session.pause()
            except Exception:
                pass
            self.session = None
