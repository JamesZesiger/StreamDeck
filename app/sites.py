"""Dynamic site registry backed by a JSON file.

SITES_FILE (default /data/sites.json, volume-mounted from ./config) is the
source of truth for which streaming sites exist. Created with the default six
sites on first startup, then synced into the services table so titles can
reference sites by FK. Sign-in happens in the browser (the user's own session
cookies with each site) — no credentials are stored anywhere.
Manual edits to the file apply on app restart.
"""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from config import settings

# tmdb_provider_id: TMDB/JustWatch watch-provider id, used by the "Add all"
# preload (discover popular titles on that provider). search_url: template for
# deep links when the exact title URL is unknown (preloaded titles).
DEFAULT_SITES = [
    {"name": "Netflix", "slug": "netflix", "base_domain": "netflix.com",
     "icon_path": "/static/icons/netflix.svg",     "tmdb_provider_id": 8,
     "search_url": "https://www.netflix.com/search?q={query}"},
    {"name": "Disney+", "slug": "disneyplus", "base_domain": "disneyplus.com",
     "icon_path": "/static/icons/disneyplus.svg",     "tmdb_provider_id": 337,
     "search_url": "https://www.disneyplus.com/search?q={query}"},
    {"name": "Hulu", "slug": "hulu", "base_domain": "hulu.com",
     "icon_path": "/static/icons/hulu.svg",     "tmdb_provider_id": 15,
     "search_url": "https://www.hulu.com/search?q={query}"},
    {"name": "Prime Video", "slug": "primevideo", "base_domain": "primevideo.com",
     "icon_path": "/static/icons/primevideo.svg",     "tmdb_provider_id": 9,
     "search_url": "https://www.primevideo.com/search?phrase={query}"},
    {"name": "Max", "slug": "max", "base_domain": "max.com",
     "icon_path": "/static/icons/max.svg",     "tmdb_provider_id": 1899,
     "search_url": "https://play.max.com/search?q={query}"},
    {"name": "YouTube", "slug": "youtube", "base_domain": "youtube.com",
     "icon_path": "/static/icons/youtube.svg",     "tmdb_provider_id": None,
     "search_url": "https://www.youtube.com/results?search_query={query}"},
]

_DEFAULTS_BY_SLUG = {s["slug"]: s for s in DEFAULT_SITES}

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
        raw = json.load(f).get("sites", [])
    # Backfill fields added after the file was created (e.g. tmdb_provider_id)
    # from the shipped defaults, without clobbering stored values.
    merged = []
    had_credentials = False
    for s in raw:
        # Credentials are retired (sign-in is the browser's own session);
        # scrub any stored ones so plaintext passwords don't linger on disk.
        had_credentials |= "username" in s or "password" in s
        base = dict(_DEFAULTS_BY_SLUG.get(s["slug"], {}))
        base.update({k: v for k, v in s.items() if v not in (None, "")})
        base.pop("username", None)
        base.pop("password", None)
        base.setdefault("tmdb_provider_id", None)
        base.setdefault("search_url", f"https://www.{base['base_domain']}")
        merged.append(base)
    if had_credentials:
        save_sites(merged)
    return merged


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


def _clean_domain(base_domain: str) -> str:
    domain = base_domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0]
    domain = domain.removeprefix("www.")
    if "." not in domain:
        raise ValueError("Base domain must look like example.com.")
    return domain


def add_site(name: str, base_domain: str,
             tmdb_provider_id: int | None = None) -> dict:
    name = name.strip()
    slug = slugify(name)
    if not slug:
        raise ValueError("Site name must contain letters or numbers.")
    sites = load_sites()
    if any(s["slug"] == slug for s in sites):
        raise ValueError(f"A site named “{name}” already exists.")
    domain = _clean_domain(base_domain)
    site = {
        "name": name,
        "slug": slug,
        "base_domain": domain,
        "icon_path": f"/icons/{slug}.svg",
        "tmdb_provider_id": tmdb_provider_id,
        "search_url": f"https://www.{domain}",
    }
    sites.append(site)
    save_sites(sites)
    return site


def update_site(slug: str, name: str, base_domain: str,
                tmdb_provider_id: int | None, search_url: str) -> dict:
    """Update a site in place. Slug is the identity and never changes."""
    sites = load_sites()
    for s in sites:
        if s["slug"] != slug:
            continue
        if name.strip():
            s["name"] = name.strip()
        s["base_domain"] = _clean_domain(base_domain)
        s["tmdb_provider_id"] = tmdb_provider_id
        if search_url.strip():
            s["search_url"] = search_url.strip()
        save_sites(sites)
        return s
    raise ValueError("Unknown site.")


def title_search_link(site: dict, query: str) -> str:
    """Deep link for a title whose exact URL we don't know: the site's search
    page for that title (or just the site) — never a scraped URL."""
    from urllib.parse import quote_plus
    tmpl = site.get("search_url") or f"https://www.{site['base_domain']}"
    return tmpl.replace("{query}", quote_plus(query)) if "{query}" in tmpl else tmpl


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
