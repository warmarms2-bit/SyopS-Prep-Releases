#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#  SYOPS UTILS - Utilidades compartidas entre syops_prep.py y los
#  módulos de descarga. Se mantiene en un archivo separado para evitar
#  importaciones circulares.
# ═══════════════════════════════════════════════════════════════════

import logging
import sys
import os
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


APP_DIR = app_dir()


# ── Logging centralizado ──────────────────────────────────────────
# Nivel por defecto: INFO. En desarrollo podés subir a DEBUG con
# SYOPS_LOG_LEVEL=DEBUG. El archivo rota a 5MB x 3 copias.
_LOG_LEVEL = os.environ.get("SYOPS_LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_DATE = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging():
    """Configura el logging global: consola + archivo rotativo.
    Idempotente: solo configura la primera vez."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE)

    # Consola: avisos y superiores (evita ruido en stdout)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Archivo: todo (INFO y superiores) con rotación
    try:
        log_dir = APP_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "syops.log", maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass


def log_error(msg: str):
    """Log de error de un solo mensaje (compatibilidad con log_error histórico)."""
    logger = logging.getLogger("syops_utils")
    logger.error(msg)
    try:
        log_path = app_dir() / "syops_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


if sys.platform == "win32":
    _NOWINDOW = subprocess.CREATE_NO_WINDOW
else:
    _NOWINDOW = 0
