"""App-wide preferences, stored in the app_prefs table (one JSON-encoded
value per key).

Holds the TMDB metadata language (every fetch asks TMDB for text in this
language; one value for the whole app, not per profile — background imports
have no profile context), the display theme, the library region, and the
parent PIN hash for kid-mode locks.

Reads are served from an in-memory cache — one process owns these values,
and Jinja globals plus tmdb.py call the getters from synchronous code, so
this module talks to the database through its own *synchronous* engine
rather than db.py's async one. Only writes touch the database; the table is
tiny and written once per settings change.

Values previously kept in prefs.json are imported on first use, so an
existing install upgrades without losing its PIN or theme. The file is left
in place as a backup and no longer read after that.
"""

import hashlib
import hmac
import json
import logging
import secrets
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from models import AppPref, Base
from config import settings

log = logging.getLogger(__name__)

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

_engine: Engine | None = None
_cache: dict | None = None  # every stored key; one process owns the table


def _sync_url() -> str:
    """db.py's URL with the async driver swapped for a sync one."""
    return settings.database_url.replace("+asyncpg", "+psycopg")


def get_engine():
    """Lazily built so importing this module never opens a connection
    (tests swap in their own engine before the first read)."""
    global _engine
    if _engine is None:
        _engine = create_engine(_sync_url(), pool_pre_ping=True)
        Base.metadata.create_all(_engine, tables=[AppPref.__table__])
    return _engine


def _legacy_file() -> Path:
    return Path(settings.sites_file).with_name("prefs.json")


def _import_legacy_file() -> dict:
    """Values from a pre-database install, or {} if there's no file."""
    try:
        data = json.loads(_legacy_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load() -> dict:
    """The whole table, cached. On the first load of an empty table, any
    prefs.json left over from a pre-database install is imported."""
    global _cache
    if _cache is None:
        with Session(get_engine()) as session:
            rows = session.execute(select(AppPref)).scalars().all()
            _cache = {r.key: json.loads(r.value) for r in rows}
            if not _cache:
                legacy = _import_legacy_file()
                for key, value in legacy.items():
                    session.add(AppPref(key=key, value=json.dumps(value)))
                if legacy:
                    session.commit()
                    log.info("Imported %d preference(s) from %s into app_prefs",
                             len(legacy), _legacy_file())
                _cache = legacy
    return _cache


def warm_cache() -> None:
    """Load the table at startup so the one-time prefs.json import (and any
    connection problem) surfaces there rather than on the first request."""
    _load()


def _get(key: str, default):
    value = _load().get(key, default)
    # A hand-edited row of the wrong type shouldn't take the app down.
    return value if isinstance(value, type(default)) else default


def _save(key: str, value) -> None:
    with Session(get_engine()) as session:
        session.merge(AppPref(key=key, value=json.dumps(value)))
        session.commit()
    _load()[key] = value


def get_language() -> str:
    return _get("language", DEFAULT_LANGUAGE)


def set_language(lang: str) -> None:
    _save("language", lang)


def get_region() -> str:
    return _get("region", DEFAULT_REGION)


def set_region(region: str) -> None:
    _save("region", region)


def get_theme() -> dict:
    stored = _get("theme", {})
    theme = dict(DEFAULT_THEME)
    theme.update({k: v for k, v in stored.items() if k in DEFAULT_THEME})
    if theme["accent"] not in ACCENTS:
        theme["accent"] = DEFAULT_THEME["accent"]
    return theme


def set_theme(theme: dict) -> None:
    _save("theme", theme)


# PBKDF2-HMAC-SHA256 iteration count, per current OWASP guidance.
PIN_ITERATIONS = 600_000


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.strip().encode(),
                                 bytes.fromhex(salt), PIN_ITERATIONS)
    return f"pbkdf2_sha256${PIN_ITERATIONS}${salt}${digest.hex()}"


def is_legacy_pin_hash(stored: str) -> bool:
    """Hashes written before salting was added: bare sha256 hex."""
    return bool(stored) and "$" not in stored


def verify_pin(pin: str, stored: str) -> bool:
    if not stored:
        return False
    if is_legacy_pin_hash(stored):
        legacy = hashlib.sha256(pin.strip().encode()).hexdigest()
        return hmac.compare_digest(legacy, stored)
    try:
        _, iterations, salt, digest = stored.split("$")
        computed = hashlib.pbkdf2_hmac("sha256", pin.strip().encode(),
                                       bytes.fromhex(salt), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(computed.hex(), digest)


def get_pin_hash() -> str:
    return _get("pin_hash", "")


def set_pin(pin: str) -> None:
    _save("pin_hash", hash_pin(pin))


def get_secret_key() -> str:
    """Key for signing short-lived tokens (the PIN-unlock cookie). Generated
    once and persisted so unlocks survive an app restart."""
    key = _get("secret_key", "")
    if not key:
        key = secrets.token_hex(32)
        _save("secret_key", key)
    return key
