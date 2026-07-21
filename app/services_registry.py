"""Known streaming services: seed data and URL → service detection."""

from urllib.parse import urlparse

SEED_SERVICES = [
    {"name": "Netflix", "slug": "netflix", "base_domain": "netflix.com",
     "icon_path": "/static/icons/netflix.svg", "playback_mode": "embedded"},
    {"name": "Disney+", "slug": "disneyplus", "base_domain": "disneyplus.com",
     "icon_path": "/static/icons/disneyplus.svg", "playback_mode": "embedded"},
    {"name": "Hulu", "slug": "hulu", "base_domain": "hulu.com",
     "icon_path": "/static/icons/hulu.svg", "playback_mode": "embedded"},
    {"name": "Prime Video", "slug": "primevideo", "base_domain": "primevideo.com",
     "icon_path": "/static/icons/primevideo.svg", "playback_mode": "embedded"},
    {"name": "Max", "slug": "max", "base_domain": "max.com",
     "icon_path": "/static/icons/max.svg", "playback_mode": "embedded"},
    {"name": "YouTube", "slug": "youtube", "base_domain": "youtube.com",
     "icon_path": "/static/icons/youtube.svg", "playback_mode": "deeplink"},
]

_DOMAIN_TO_SLUG = {s["base_domain"]: s["slug"] for s in SEED_SERVICES}
# Common alternate domains
_DOMAIN_TO_SLUG.update({
    "amazon.com": "primevideo",
    "youtu.be": "youtube",
    "hbomax.com": "max",
})


def detect_service_slug(url: str) -> str | None:
    """Map a pasted streaming URL to a known service slug by domain suffix."""
    host = (urlparse(url).hostname or "").lower()
    for domain, slug in _DOMAIN_TO_SLUG.items():
        if host == domain or host.endswith("." + domain):
            return slug
    return None
