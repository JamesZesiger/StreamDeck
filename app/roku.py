"""Roku ECP launch mapping for the sideloaded StreamDeck Roku channel.

Titles store browser deep links (see wikidata.SERVICE_PROPS for the URL
shapes). A Roku can't open a browser URL, but ECP can launch an installed
channel straight into a title: POST /launch/{channel_id}?contentId=...&
mediaType=... . This module maps a service slug + stored deep_link to those
launch parameters. Channel ids and contentId formats are community-documented,
not an official Roku contract — they may drift; keep all fixes here.
"""

import re
from urllib.parse import quote

import sites

# slug -> Roku channel id + regex that pulls the service-native content id out
# of the stored deep_link. media_type "tv" maps to ECP mediaType "series".
ROKU_APPS: dict[str, dict] = {
    "netflix": {
        "channel_id": 12,
        "patterns": [r"netflix\.com/title/(\d+)"],
    },
    "primevideo": {
        "channel_id": 13,
        "patterns": [r"primevideo\.com/detail/([^/?#]+)"],
    },
    "hulu": {
        "channel_id": 2285,
        "patterns": [r"hulu\.com/(?:movie|series)/([0-9a-f-]{36})"],
    },
    "disneyplus": {
        "channel_id": 291097,
        "patterns": [r"disneyplus\.com/(?:movies/wd|series/wp)/([^/?#]+)"],
    },
    "max": {
        "channel_id": 61322,
        # play.max.com/{id} where id may be a bare UUID/urn or have a
        # movie/show prefix; take the last non-empty path segment.
        "patterns": [r"play\.max\.com/(?:[^/?#]+/)*([^/?#]+)"],
    },
    "youtube": {
        "channel_id": 837,
        "patterns": [r"[?&]v=([\w-]{11})", r"youtu\.be/([\w-]{11})"],
        # YouTube's Roku channel takes a bare video id, no mediaType.
        "omit_media_type": True,
    },
    "crunchyroll": {
        "channel_id": 2595,
        "patterns": [r"crunchyroll\.com/series/([^/?#]+)"],
    },
}


def channel_id(slug: str) -> int | None:
    app = ROKU_APPS.get(slug)
    return app["channel_id"] if app else None


def _is_search_fallback(slug: str, deep_link: str) -> bool:
    """A deep_link that still starts like the site's search template was
    never resolved to a real title URL (same test as _backfill_deep_links)."""
    site = sites.get_site(slug)
    template = (site or {}).get("search_url") or ""
    prefix = template.split("{query}")[0] if "{query}" in template else template
    return bool(prefix) and deep_link.startswith(prefix)


def parse_content_id(slug: str, deep_link: str) -> str | None:
    app = ROKU_APPS.get(slug)
    if not app or not deep_link or _is_search_fallback(slug, deep_link):
        return None
    for pattern in app["patterns"]:
        m = re.search(pattern, deep_link)
        if m:
            return m.group(1)
    return None


def launch_params(slug: str, media_type: str, deep_link: str) -> dict | None:
    """ECP launch parameters for one provider row, or None when the service
    has no Roku channel mapping (custom sites). content_id is None when the
    deep link is a search fallback or unparseable — the ecp_path then just
    opens the channel's home screen."""
    app = ROKU_APPS.get(slug)
    if not app:
        return None
    cid = parse_content_id(slug, deep_link)
    ecp_media = None
    path = f"/launch/{app['channel_id']}"
    if cid:
        # Prime GTIs contain "." and ":"; quote everything but leave nothing
        # unescaped that ECP would misparse.
        path += f"?contentId={quote(cid, safe='')}"
        if not app.get("omit_media_type"):
            ecp_media = "series" if media_type == "tv" else "movie"
            path += f"&mediaType={ecp_media}"
    return {
        "channel_id": app["channel_id"],
        "content_id": cid,
        "media_type": ecp_media,
        "ecp_path": path,
    }
