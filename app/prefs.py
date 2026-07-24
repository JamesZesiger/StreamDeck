"""App-wide preferences, stored in prefs.json next to sites.json in /data.

Holds the TMDB metadata language (every fetch asks TMDB for text in this
language; one value for the whole app, not per profile — background imports
have no profile context) and the parent PIN hash for kid-mode locks.
"""

import hashlib
import json
import secrets
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

_language: str | None = None  # in-memory cache; one process owns the file
_region: str | None = None


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


def _save(key: str, value: str) -> None:
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


_session_secret: str | None = None


def get_session_secret() -> str:
    """HMAC key for session cookies, generated once and persisted so
    sessions survive restarts."""
    global _session_secret
    if _session_secret is None:
        try:
            _session_secret = json.loads(_path().read_text()).get(
                "session_secret", "")
        except (OSError, ValueError):
            _session_secret = ""
        if not _session_secret:
            _session_secret = secrets.token_hex(32)
            _save("session_secret", _session_secret)
    return _session_secret


def get_admin_user() -> str:
    try:
        return json.loads(_path().read_text()).get("admin_user", "")
    except (OSError, ValueError):
        return ""


def get_admin_hash() -> str:
    try:
        return json.loads(_path().read_text()).get("admin_hash", "")
    except (OSError, ValueError):
        return ""


def set_admin(username: str, password_hash: str) -> None:
    """The /admin area's credentials — separate from user accounts."""
    _save("admin_user", username)
    _save("admin_hash", password_hash)


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.strip().encode()).hexdigest()


def get_pin_hash() -> str:
    try:
        return json.loads(_path().read_text()).get("pin_hash", "")
    except (OSError, ValueError):
        return ""


def set_pin(pin: str) -> None:
    _save("pin_hash", hash_pin(pin))
