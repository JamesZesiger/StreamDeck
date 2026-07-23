"""Minimal async TMDB client. Only metadata comes from here — never from streaming sites."""

import httpx

import prefs
from config import settings

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"

# TMDB has no "browse collections" endpoint, so the carousel samples from a
# curated set of well-known franchise collections (ids verified against the
# API). All names end in "Collection" on TMDB.
CURATED_COLLECTIONS = [
    10,      # Star Wars
    1241,    # Harry Potter
    86311,   # The Avengers
    263,     # The Dark Knight
    645,     # James Bond
    528,     # The Terminator
    84,      # Indiana Jones
    2344,    # The Matrix
    119,     # The Lord of the Rings
    121938,  # The Hobbit
    295,     # Pirates of the Caribbean
    87359,   # Mission: Impossible
    328,     # Jurassic Park
    9485,    # The Fast and the Furious
    748,     # X-Men
    8650,    # Transformers
    8091,    # Alien
    1575,    # Rocky
    2980,    # Ghostbusters
    556,     # Spider-Man
    420,     # The Chronicles of Narnia
    87096,   # Avatar
    10194,   # Toy Story
    2150,    # Shrek
    86066,   # Despicable Me
    230,     # The Godfather
    264,     # Back to the Future
    1570,    # Die Hard
    8945,    # Mad Max
    404609,  # John Wick
    131635,  # The Hunger Games
    33514,   # Twilight
]


def _img(path: str | None, size: str) -> str:
    return f"{IMG}/{size}{path}" if path else ""


async def search_multi(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/search/multi",
            params={"api_key": settings.tmdb_api_key, "query": query,
                    "include_adult": "false", "language": prefs.get_language()},
        )
        r.raise_for_status()
    results = []
    for item in r.json().get("results", []):
        if item.get("media_type") not in ("movie", "tv"):
            continue
        date = item.get("release_date") or item.get("first_air_date") or ""
        results.append({
            "tmdb_id": item["id"],
            "media_type": item["media_type"],
            "title": item.get("title") or item.get("name") or "",
            "overview": item.get("overview") or "",
            "poster_url": _img(item.get("poster_path"), "w342"),
            "year": int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
        })
    return results


async def discover_by_provider(provider_id: int, media_type: str,
                               limit: int | None = 20, region: str = "US",
                               min_votes: int = 200) -> list[int]:
    """Titles currently on a watch provider (JustWatch data via TMDB) — returns
    TMDB ids, most popular first. No streaming site is touched.

    limit=None pulls the provider's entire catalog (all TMDB pages, capped at
    the API's 500-page hard limit). min_votes=0 drops the popularity floor so
    obscure/long-tail titles are included too."""
    ids: list[int] = []
    page = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while limit is None or len(ids) < limit:
            # TMDB refuses page numbers above 500, regardless of total_pages.
            if page > 500:
                break
            params = {
                "api_key": settings.tmdb_api_key,
                "with_watch_providers": provider_id,
                "watch_region": region,
                "sort_by": "popularity.desc",
                "page": page,
            }
            # TMDB popularity is easily gamed by obscure titles; an optional
            # audience floor keeps "top" lists recognizable.
            if min_votes:
                params["vote_count.gte"] = min_votes
            r = await client.get(f"{BASE}/discover/{media_type}", params=params)
            r.raise_for_status()
            data = r.json()
            ids.extend(item["id"] for item in data.get("results", []))
            if page >= data.get("total_pages", 1):
                break
            page += 1
    return ids if limit is None else ids[:limit]


async def get_collection(collection_id: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/collection/{collection_id}",
            params={"api_key": settings.tmdb_api_key,
                    "language": prefs.get_language()},
        )
        r.raise_for_status()
    d = r.json()
    parts = sorted((d.get("parts") or []),
                   key=lambda p: p.get("release_date") or "9999")
    return {
        "id": d["id"],
        "name": d.get("name") or "",
        "overview": d.get("overview") or "",
        "backdrop_url": _img(d.get("backdrop_path"), "w1280"),
        "poster_url": _img(d.get("poster_path"), "w342"),
        "parts": [{
            "title": p.get("title") or "",
            "poster_url": _img(p.get("poster_path"), "w185"),
        } for p in parts if p.get("poster_path")],
    }


async def get_details(tmdb_id: int, media_type: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}",
            params={"api_key": settings.tmdb_api_key,
                    "language": prefs.get_language()},
        )
        r.raise_for_status()
    d = r.json()
    if media_type == "movie":
        runtime = d.get("runtime")
        date = d.get("release_date") or ""
        title = d.get("title") or ""
    else:
        runtimes = d.get("episode_run_time") or []
        runtime = runtimes[0] if runtimes else None
        date = d.get("first_air_date") or ""
        title = d.get("name") or ""
    return {
        "tmdb_id": d["id"],
        "media_type": media_type,
        "title": title,
        "overview": d.get("overview") or "",
        "poster_url": _img(d.get("poster_path"), "w500"),
        "backdrop_url": _img(d.get("backdrop_path"), "w1280"),
        "runtime_minutes": runtime,
        "release_year": int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
        "genres": ", ".join(g["name"] for g in d.get("genres", [])),
        "mature": bool(d.get("adult")),
        "rating": d.get("vote_average"),
        "vote_count": d.get("vote_count"),
        "popularity": d.get("popularity"),
    }
