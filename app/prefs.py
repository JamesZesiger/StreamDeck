"""App-wide preferences, stored in prefs.json next to sites.json in /data.

Currently just the TMDB metadata language: every fetch (search, details,
imports, collections) asks TMDB for text in this language. One value for the
whole app, not per profile — background imports have no profile context.
"""

import json
from pathlib import Path

from config import settings

DEFAULT_LANGUAGE = "en-US"

# (TMDB language code, toolbar abbreviation, native name)
LANGUAGES = [
    ("en-US", "EN", "English"),
    ("es-ES", "ES", "Español"),
    ("fr-FR", "FR", "Français"),
    ("de-DE", "DE", "Deutsch"),
    ("it-IT", "IT", "Italiano"),
    ("pt-BR", "PT", "Português"),
    ("ja-JP", "JA", "日本語"),
    ("ko-KR", "KO", "한국어"),
    ("zh-CN", "ZH", "中文"),
    ("hi-IN", "HI", "हिन्दी"),
]

_language: str | None = None  # in-memory cache; one process owns the file


def _path() -> Path:
    return Path(settings.sites_file).with_name("prefs.json")


def get_language() -> str:
    global _language
    if _language is None:
        try:
            _language = json.loads(_path().read_text()).get(
                "language", DEFAULT_LANGUAGE)
        except (OSError, ValueError):
            _language = DEFAULT_LANGUAGE
    return _language


def set_language(lang: str) -> None:
    global _language
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        data = {}
    data["language"] = lang
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)
    _language = lang
