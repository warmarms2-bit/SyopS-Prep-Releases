import json
import sys
from pathlib import Path

_current_lang = "es"
_strings = {}
_lang_path = None

LANGUAGES = {
    "es": "Espa\u00f1ol",
    "en": "English",
}

def _get_locale_dir():
    if getattr(sys, "frozen", False):
        # En el bundle de PyInstaller los datos pueden quedar directamente en
        # sys._MEIPASS o dentro de una subcarpeta "locale" segun como se haya
        # empaquetado. Probamos ambas ubicaciones para ser robustos.
        candidates = [Path(sys._MEIPASS) / "locale", Path(sys._MEIPASS)]
        for c in candidates:
            if c.exists() and any(c.glob("*.json")):
                return c
        return Path(sys._MEIPASS) / "locale"
    return Path(__file__).parent / "locale"

def load_language(lang_code: str):
    global _current_lang, _strings, _lang_path
    if lang_code not in LANGUAGES:
        lang_code = "es"
    locale_dir = _get_locale_dir()
    path = locale_dir / f"{lang_code}.json"
    if not path.exists():
        fallback = locale_dir / "es.json"
        if fallback.exists():
            path = fallback
            lang_code = "es"
        else:
            _strings = {}
            _current_lang = lang_code
            return
    try:
        with open(path, "r", encoding="utf-8") as f:
            _strings = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        # A malformed locale must not prevent the installer from starting.
        # English can still fall back to Spanish while copy is being edited.
        fallback = locale_dir / "es.json"
        if lang_code != "es" and fallback.exists() and fallback != path:
            try:
                with open(fallback, "r", encoding="utf-8") as f:
                    _strings = json.load(f)
                _current_lang = "es"
                _lang_path = fallback
                return
            except (OSError, json.JSONDecodeError):
                pass
        print(f"[i18n] No se pudo cargar {path.name}: {exc}")
        _strings = {}
    _current_lang = lang_code
    _lang_path = path

def _(key: str, **kwargs) -> str:
    val = _strings
    for part in key.split("."):
        if isinstance(val, dict):
            val = val.get(part, None)
        else:
            return key
    if val is None:
        return key
    if isinstance(val, str) and kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return val if isinstance(val, str) else key

def current_language() -> str:
    return _current_lang

def available_languages() -> list:
    return list(LANGUAGES.keys())

load_language("es")
