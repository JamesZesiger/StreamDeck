"""Minimal async TMDB client. Only metadata comes from here — never from streaming sites."""

from datetime import date

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
        released = item.get("release_date") or item.get("first_air_date") or ""
        results.append({
            "tmdb_id": item["id"],
            "media_type": item["media_type"],
            "title": item.get("title") or item.get("name") or "",
            "overview": item.get("overview") or "",
            "poster_url": _img(item.get("poster_path"), "w342"),
            "year": int(released[:4]) if len(released) >= 4 and released[:4].isdigit() else None,
        })
    return results


async def discover_by_provider(provider_id: int, media_type: str,
                               limit: int | None = 20, region: str | None = None,
                               min_votes: int = 200) -> list[int]:
    """Titles currently on a watch provider (JustWatch data via TMDB) — returns
    TMDB ids, most popular first. No streaming site is touched.

    limit=None pulls the provider's entire catalog (all TMDB pages, capped at
    the API's 500-page hard limit). min_votes=0 drops the popularity floor so
    obscure/long-tail titles are included too."""
    # Imports follow the app's region pref, so "Add all" pulls the catalog
    # the selected region can actually watch.
    region = region or prefs.get_region() or "US"
    ids: list[int] = []
    seen: set[int] = set()
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
            # Popularity shifts while paging, so a title can turn up on two
            # pages; keep only its first (most popular) appearance.
            for item in data.get("results", []):
                if item["id"] not in seen:
                    seen.add(item["id"])
                    ids.append(item["id"])
            if page >= data.get("total_pages", 1):
                break
            page += 1
    return ids if limit is None else ids[:limit]


async def get_recommendations(tmdb_id: int, media_type: str) -> list[dict]:
    """TMDB's 'people also liked' list for one title (first page only) —
    lightweight candidates for the Discover page; details come later."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/recommendations",
            params={"api_key": settings.tmdb_api_key,
                    "language": prefs.get_language()},
        )
        r.raise_for_status()
    out = []
    for item in r.json().get("results", []):
        mt = item.get("media_type") or media_type
        if mt not in ("movie", "tv"):
            continue
        out.append({"tmdb_id": item["id"], "media_type": mt,
                    "popularity": item.get("popularity") or 0.0})
    return out


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
                    "language": prefs.get_language(),
                    "append_to_response": ("release_dates,external_ids,watch/providers"
                                           if media_type == "movie"
                                           else "content_ratings,external_ids,watch/providers")},
        )
        r.raise_for_status()
    d = r.json()
    certification = ""
    if media_type == "movie":
        runtime = d.get("runtime")
        released = d.get("release_date") or ""
        title = d.get("title") or ""
        for entry in d.get("release_dates", {}).get("results", []):
            if entry.get("iso_3166_1") == "US":
                certification = next(
                    (rel["certification"] for rel in entry.get("release_dates", [])
                     if rel.get("certification")), "")
                break
    else:
        runtimes = d.get("episode_run_time") or []
        runtime = runtimes[0] if runtimes else None
        released = d.get("first_air_date") or ""
        title = d.get("name") or ""
        for entry in d.get("content_ratings", {}).get("results", []):
            if entry.get("iso_3166_1") == "US":
                certification = entry.get("rating") or ""
                break
    return {
        "tmdb_id": d["id"],
        "media_type": media_type,
        "title": title,
        "overview": d.get("overview") or "",
        "poster_url": _img(d.get("poster_path"), "w500"),
        "backdrop_url": _img(d.get("backdrop_path"), "w1280"),
        "runtime_minutes": runtime,
        "release_year": (int(released[:4])
                         if len(released) >= 4 and released[:4].isdigit() else None),
        "genres": ", ".join(g["name"] for g in d.get("genres", [])),
        "mature": bool(d.get("adult")),
        "rating": d.get("vote_average"),
        "vote_count": d.get("vote_count"),
        "popularity": d.get("popularity"),
        "certification": certification,
        "imdb_id": (d.get("external_ids") or {}).get("imdb_id") or "",
        "provider_regions": _provider_regions(
            d.get("watch/providers", {}).get("results")),
    }


def _provider_regions(results: dict | None) -> dict:
    """{country code: {provider ids streaming it there}} — flatrate/free/ads
    offers only (rent/buy isn't "watchable on the service")."""
    return {
        country: ids
        for country, offers in (results or {}).items()
        if (ids := {p["provider_id"]
                    for kind in ("flatrate", "free", "ads")
                    for p in offers.get(kind, [])})
    }


async def get_providers(tmdb_id: int, media_type: str) -> dict:
    """Just the watch-provider map for a title — the availability refresh
    re-checks the whole library, so this stays one cheap call per title."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/watch/providers",
            params={"api_key": settings.tmdb_api_key},
        )
        r.raise_for_status()
    return _provider_regions(r.json().get("results"))


def regions_for_provider(provider_regions: dict, provider_id: int | None) -> str:
    """Comma-separated country codes where this provider streams the title."""
    if not provider_id:
        return ""
    return ", ".join(sorted(
        c for c, ids in provider_regions.items() if provider_id in ids))


async def get_upcoming(limit: int = 8) -> list[dict]:
    """Upcoming theatrical movies (region-aware) and soon-to-air shows,
    soonest first — for the library's Coming Soon banner. Only titles with a
    backdrop make the cut; they're hero slides."""
    region = prefs.get_region() or "US"
    lang = prefs.get_language()
    today = date.today().isoformat()
    async with httpx.AsyncClient(timeout=15) as client:
        r_movies = await client.get(
            f"{BASE}/movie/upcoming",
            params={"api_key": settings.tmdb_api_key, "language": lang,
                    "region": region})
        r_movies.raise_for_status()
        r_tv = await client.get(
            f"{BASE}/discover/tv",
            params={"api_key": settings.tmdb_api_key, "language": lang,
                    "first_air_date.gte": today,
                    "sort_by": "popularity.desc"})
        r_tv.raise_for_status()
    items = []
    for mt, results, date_field, name_field in (
            ("movie", r_movies.json().get("results", []), "release_date", "title"),
            ("tv", r_tv.json().get("results", []), "first_air_date", "name")):
        for item in results:
            when = item.get(date_field) or ""
            if when < today or not item.get("backdrop_path") or item.get("adult"):
                continue
            items.append({
                "tmdb_id": item["id"],
                "media_type": mt,
                "title": item.get(name_field) or "",
                "overview": item.get("overview") or "",
                "backdrop_url": _img(item["backdrop_path"], "w1280"),
                "release_date": when,
                "popularity": item.get("popularity") or 0.0,
            })
    # Soonest first; popularity breaks same-day ties so slides stay recognizable.
    items.sort(key=lambda i: (i["release_date"], -i["popularity"]))
    return items[:limit]


async def get_seasons(tmdb_id: int) -> list[dict]:
    """A show's seasons (specials excluded): number, name, episode count."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/tv/{tmdb_id}",
            params={"api_key": settings.tmdb_api_key,
                    "language": prefs.get_language()},
        )
        r.raise_for_status()
    return [{
        "season_number": s["season_number"],
        "name": s.get("name") or f"Season {s['season_number']}",
        "episode_count": s.get("episode_count") or 0,
    } for s in r.json().get("seasons", [])
        if s.get("season_number", 0) > 0 and (s.get("episode_count") or 0) > 0]


async def get_season_episodes(tmdb_id: int, season_number: int) -> list[dict]:
    """One season's episode list: number, name, air date."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/tv/{tmdb_id}/season/{season_number}",
            params={"api_key": settings.tmdb_api_key,
                    "language": prefs.get_language()},
        )
        r.raise_for_status()
    return [{
        "episode": e["episode_number"],
        "name": e.get("name") or f"Episode {e['episode_number']}",
        "air_date": e.get("air_date") or "",
    } for e in r.json().get("episodes", [])]


async def get_trailer(tmdb_id: int, media_type: str) -> dict | None:
    """Best YouTube trailer for a title ({key, name}), or None. Prefers
    official trailers over teasers; asks in the app language but falls back
    to English/untagged uploads so non-English setups still get one."""
    lang = prefs.get_language()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/videos",
            params={"api_key": settings.tmdb_api_key, "language": lang,
                    "include_video_language": f"{lang.split('-')[0]},en,null"},
        )
        r.raise_for_status()
    videos = [v for v in r.json().get("results", [])
              if v.get("site") == "YouTube" and v.get("key")
              and v.get("type") in ("Trailer", "Teaser")]
    if not videos:
        return None
    best = max(videos, key=lambda v: (v.get("type") == "Trailer",
                                      bool(v.get("official")),
                                      v.get("published_at") or ""))
    return {"key": best["key"], "name": best.get("name") or "Trailer"}


async def get_imdb_id(tmdb_id: int, media_type: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/external_ids",
            params={"api_key": settings.tmdb_api_key},
        )
        r.raise_for_status()
    return r.json().get("imdb_id") or ""
