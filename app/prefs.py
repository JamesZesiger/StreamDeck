"""App-wide preferences, stored in prefs.json next to sites.json in /data.

Holds the TMDB metadata language (every fetch asks TMDB for text in this
language; one value for the whole app, not per profile — background imports
have no profile context) and the parent PIN hash for kid-mode locks.
"""

import hashlib
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

DEFAULT_REGION = "US"

# (ISO country code, name) choices for the toolbar region picker; the library
# only shows titles watchable in this region ("" = everywhere).
REGIONS = [
    ("US", "United States"),
    ("CA", "Canada"),
    ("GB", "United Kingdom"),
    ("AU", "Australia"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("ES", "Spain"),
    ("IT", "Italy"),
    ("BR", "Brazil"),
    ("MX", "Mexico"),
    ("NL", "Netherlands"),
    ("JP", "Japan"),
    ("KR", "South Korea"),
    ("IN", "India"),
]

# Accent palettes: Tailwind v3 hexes for every red-* shade the templates
# use. The chosen one is injected as tailwind.config's `red` scale in
# base.html, restyling every accent class at once.
ACCENTS = {
    "red":     {"300": "#fca5a5", "400": "#f87171", "500": "#ef4444",
                "600": "#dc2626", "700": "#b91c1c", "900": "#7f1d1d"},
    "orange":  {"300": "#fdba74", "400": "#fb923c", "500": "#f97316",
                "600": "#ea580c", "700": "#c2410c", "900": "#7c2d12"},
    "amber":   {"300": "#fcd34d", "400": "#fbbf24", "500": "#f59e0b",
                "600": "#d97706", "700": "#b45309", "900": "#78350f"},
    "emerald": {"300": "#6ee7b7", "400": "#34d399", "500": "#10b981",
                "600": "#059669", "700": "#047857", "900": "#064e3b"},
    "cyan":    {"300": "#67e8f9", "400": "#22d3ee", "500": "#06b6d4",
                "600": "#0891b2", "700": "#0e7490", "900": "#164e63"},
    "blue":    {"300": "#93c5fd", "400": "#60a5fa", "500": "#3b82f6",
                "600": "#2563eb", "700": "#1d4ed8", "900": "#1e3a8a"},
    "violet":  {"300": "#c4b5fd", "400": "#a78bfa", "500": "#8b5cf6",
                "600": "#7c3aed", "700": "#6d28d9", "900": "#4c1d95"},
    "pink":    {"300": "#f9a8d4", "400": "#f472b6", "500": "#ec4899",
                "600": "#db2777", "700": "#be185d", "900": "#831843"},
}

# bg_mode: solid = flat bg_from; gradient = bg_from→bg_to at bg_angle;
# animated = the same gradient slowly drifting.
DEFAULT_THEME = {
    "accent": "red",
    "bg_mode": "solid",
    "bg_from": "#09090b",  # zinc-950, the original background
    "bg_to": "#1e1b4b",
    "bg_angle": 160,
}

_language: str | None = None  # in-memory cache; one process owns the file
_region: str | None = None
_theme: dict | None = None


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


def _save(key: str, value) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        data = {}
    data[key] = value
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def set_language(lang: str) -> None:
    global _language
    _save("language", lang)
    _language = lang


def get_region() -> str:
    global _region
    if _region is None:
        try:
            _region = json.loads(_path().read_text()).get(
                "region", DEFAULT_REGION)
        except (OSError, ValueError):
            _region = DEFAULT_REGION
    return _region


def set_region(region: str) -> None:
    global _region
    _save("region", region)
    _region = region


def get_theme() -> dict:
    global _theme
    if _theme is None:
        try:
            stored = json.loads(_path().read_text()).get("theme", {})
        except (OSError, ValueError):
            stored = {}
        theme = dict(DEFAULT_THEME)
        theme.update({k: v for k, v in stored.items() if k in DEFAULT_THEME})
        if theme["accent"] not in ACCENTS:
            theme["accent"] = DEFAULT_THEME["accent"]
        _theme = theme
    return _theme


def set_theme(theme: dict) -> None:
    global _theme
    _save("theme", theme)
    _theme = None  # re-merge with defaults on next read


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.strip().encode()).hexdigest()


def get_pin_hash() -> str:
    try:
        return json.loads(_path().read_text()).get("pin_hash", "")
    except (OSError, ValueError):
        return ""


def set_pin(pin: str) -> None:
    _save("pin_hash", hash_pin(pin))
