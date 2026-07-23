"""Best-effort direct deep links from Wikidata's streaming-service IDs.

TMDB never exposes per-service deep links, but Wikidata catalogues many
titles' Netflix/Disney+/Hulu/... ids (e.g. P1874 = Netflix ID). We resolve
IMDb ids (from TMDB's external_ids) through the public SPARQL endpoint in
batches and build direct title URLs. Coverage is partial — titles Wikidata
doesn't know, and sites with no mapped property, keep the site's
search?q={query} fallback link.
"""

import logging

import httpx

log = logging.getLogger(__name__)

SPARQL = "https://query.wikidata.org/sparql"
# The Wikidata query service requires an identifying User-Agent.
USER_AGENT = "StreamDeck/1.0 (self-hosted personal library)"
BATCH = 50

# slug -> media_type -> (wikidata property, url template).
# Templates come from each property's formatter URL (P1630).
SERVICE_PROPS = {
    "netflix": {
        "movie": ("P1874", "https://www.netflix.com/title/{id}"),
        "tv": ("P1874", "https://www.netflix.com/title/{id}"),
    },
    "disneyplus": {
        "movie": ("P7595", "https://www.disneyplus.com/movies/wd/{id}"),
        "tv": ("P7596", "https://www.disneyplus.com/series/wp/{id}"),
    },
    "hulu": {
        "movie": ("P6466", "https://www.hulu.com/movie/{id}"),
        "tv": ("P6467", "https://www.hulu.com/series/{id}"),
    },
    "primevideo": {
        "movie": ("P8055", "https://www.primevideo.com/detail/{id}"),
        "tv": ("P8055", "https://www.primevideo.com/detail/{id}"),
    },
    "max": {
        "movie": ("P8298", "https://play.max.com/{id}"),
        "tv": ("P8298", "https://play.max.com/{id}"),
    },
    "crunchyroll": {
        "movie": ("P11330", "https://www.crunchyroll.com/series/{id}"),
        "tv": ("P11330", "https://www.crunchyroll.com/series/{id}"),
    },
}


def supported(slug: str) -> bool:
    return slug in SERVICE_PROPS


async def resolve_links(slug: str, wanted: list[tuple[str, str]]) -> dict[str, str]:
    """{imdb_id: deep link} for (imdb_id, media_type) pairs on one service.
    Best-effort: endpoint trouble just yields fewer links, never an error."""
    props = SERVICE_PROPS.get(slug)
    if not props:
        return {}
    by_type: dict[str, list[str]] = {"movie": [], "tv": []}
    for imdb_id, media_type in wanted:
        if imdb_id and media_type in by_type and imdb_id not in by_type[media_type]:
            by_type[media_type].append(imdb_id)

    links: dict[str, str] = {}
    async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for media_type, ids in by_type.items():
            prop, template = props[media_type]
            for start in range(0, len(ids), BATCH):
                chunk = ids[start:start + BATCH]
                values = " ".join(f'"{i}"' for i in chunk)
                query = (
                    "SELECT ?imdb ?sid WHERE { VALUES ?imdb { " + values + " } "
                    "?item wdt:P345 ?imdb . ?item wdt:" + prop + " ?sid . }"
                )
                try:
                    r = await client.get(
                        SPARQL, params={"query": query, "format": "json"})
                    r.raise_for_status()
                    for row in r.json()["results"]["bindings"]:
                        links.setdefault(row["imdb"]["value"],
                                         template.format(id=row["sid"]["value"]))
                except Exception:
                    log.warning("Wikidata lookup failed for %s/%s (%d ids)",
                                slug, media_type, len(chunk))
    return links
