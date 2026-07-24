"""Site helpers. Sites live in the services table, one set per account —
DEFAULT_SITES seeds each new account at registration, and site CRUD edits
the account's rows directly. sites.json (the pre-account source of truth)
is only read once at startup to migrate legacy rows. Sign-in happens in the
browser (the user's own session cookies with each site) — no credentials
are stored anywhere.
"""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

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

ALT_DOMAINS = {
    "amazon.com": "primevideo",
    "youtu.be": "youtube",
    "hbomax.com": "max",
}

ICON_COLORS = ["#b1060f", "#0a3d91", "#1ca66c", "#1399ff", "#2723c8",
               "#e02020", "#9333ea", "#0d9488", "#ca8a04", "#db2777"]


def load_legacy_sites() -> list[dict]:
    """The pre-account sites.json contents, for the one-time startup
    migration into the services table. [] when absent or unreadable."""
    try:
        return json.loads(Path(settings.sites_file).read_text()).get("sites", [])
    except (OSError, ValueError):
        return []


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def clean_domain(base_domain: str) -> str:
    domain = base_domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0]
    domain = domain.removeprefix("www.")
    if "." not in domain:
        raise ValueError("Base domain must look like example.com.")
    return domain


def title_search_link(search_url: str, base_domain: str, query: str) -> str:
    """Deep link for a title whose exact URL we don't know: the site's search
    page for that title (or just the site) — never a scraped URL."""
    tmpl = search_url or f"https://www.{base_domain}"
    return tmpl.replace("{query}", quote_plus(query)) if "{query}" in tmpl else tmpl


def detect_service(url: str, services):
    """The Service row (from the given account's services) a URL belongs to,
    or None. Alternate domains (youtu.be, ...) map onto the matching slug."""
    host = (urlparse(url).hostname or "").lower()

    def matches(domain: str) -> bool:
        return host == domain or host.endswith("." + domain)

    for s in services:
        if matches(s.base_domain):
            return s
    by_slug = {s.slug: s for s in services}
    for domain, slug in ALT_DOMAINS.items():
        if matches(domain) and slug in by_slug:
            return by_slug[slug]
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
