"""Dynamic site registry backed by a JSON file.

SITES_FILE (default /data/sites.json, volume-mounted from ./config) is the
source of truth for which streaming sites exist and their sign-in credentials.
Created with the default six sites on first startup, then synced into the
services table so titles can reference sites by FK. Credentials live only in
the JSON file (or legacy SVC_* env vars) — never in the database.
Manual edits to the file apply on app restart.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from config import settings

DEFAULT_SITES = [
    {"name": "Netflix", "slug": "netflix", "base_domain": "netflix.com",
     "icon_path": "/static/icons/netflix.svg", "playback_mode": "embedded",
     "username": "", "password": ""},
    {"name": "Disney+", "slug": "disneyplus", "base_domain": "disneyplus.com",
     "icon_path": "/static/icons/disneyplus.svg", "playback_mode": "embedded",
     "username": "", "password": ""},
    {"name": "Hulu", "slug": "hulu", "base_domain": "hulu.com",
     "icon_path": "/static/icons/hulu.svg", "playback_mode": "embedded",
     "username": "", "password": ""},
    {"name": "Prime Video", "slug": "primevideo", "base_domain": "primevideo.com",
     "icon_path": "/static/icons/primevideo.svg", "playback_mode": "embedded",
     "username": "", "password": ""},
    {"name": "Max", "slug": "max", "base_domain": "max.com",
     "icon_path": "/static/icons/max.svg", "playback_mode": "embedded",
     "username": "", "password": ""},
    {"name": "YouTube", "slug": "youtube", "base_domain": "youtube.com",
     "icon_path": "/static/icons/youtube.svg", "playback_mode": "deeplink",
     "username": "", "password": ""},
]

ALT_DOMAINS = {
    "amazon.com": "primevideo",
    "youtu.be": "youtube",
    "hbomax.com": "max",
}

ICON_COLORS = ["#b1060f", "#0a3d91", "#1ca66c", "#1399ff", "#2723c8",
               "#e02020", "#9333ea", "#0d9488", "#ca8a04", "#db2777"]


def _path() -> Path:
    return Path(settings.sites_file)


def load_sites() -> list[dict]:
    p = _path()
    if not p.exists():
        save_sites([dict(s) for s in DEFAULT_SITES])
        return [dict(s) for s in DEFAULT_SITES]
    with p.open() as f:
        return json.load(f).get("sites", [])


def save_sites(sites: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump({"sites": sites}, f, indent=2)
    tmp.replace(p)


def get_site(slug: str) -> dict | None:
    return next((s for s in load_sites() if s["slug"] == slug), None)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def add_site(name: str, base_domain: str, playback_mode: str,
             username: str = "", password: str = "") -> dict:
    name = name.strip()
    slug = slugify(name)
    if not slug:
        raise ValueError("Site name must contain letters or numbers.")
    sites = load_sites()
    if any(s["slug"] == slug for s in sites):
        raise ValueError(f"A site named “{name}” already exists.")
    domain = base_domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0]
    domain = domain.removeprefix("www.")
    if "." not in domain:
        raise ValueError("Base domain must look like example.com.")
    site = {
        "name": name,
        "slug": slug,
        "base_domain": domain,
        "icon_path": f"/icons/{slug}.svg",
        "playback_mode": playback_mode,
        "username": username,
        "password": password,
    }
    sites.append(site)
    save_sites(sites)
    return site


def get_credentials(slug: str) -> dict[str, str] | None:
    site = get_site(slug) or {}
    key = slug.upper().replace("-", "")
    username = site.get("username") or os.environ.get(f"SVC_{key}_USERNAME", "")
    password = site.get("password") or os.environ.get(f"SVC_{key}_PASSWORD", "")
    if not username and not password:
        return None
    return {"username": username, "password": password}


def detect_service_slug(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    domains = dict(ALT_DOMAINS)
    domains.update({s["base_domain"]: s["slug"] for s in load_sites()})
    for domain, slug in domains.items():
        if host == domain or host.endswith("." + domain):
            return slug
    return None


def icon_svg(slug: str, name: str) -> str:
    """Letter-badge SVG for custom sites (seeded sites ship static files)."""
    color = ICON_COLORS[int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(ICON_COLORS)]
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"
    size = 28 if len(initials) == 1 else 22
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="12" fill="{color}"/>'
        f'<text x="32" y="42" font-family="Arial, sans-serif" font-size="{size}" '
        f'font-weight="bold" fill="#fff" text-anchor="middle">{initials}</text></svg>'
    )
