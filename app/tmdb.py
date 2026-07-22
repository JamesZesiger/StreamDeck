"""Minimal async TMDB client. Only metadata comes from here — never from streaming sites."""

import httpx

from config import settings

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"


def _img(path: str | None, size: str) -> str:
    return f"{IMG}/{size}{path}" if path else ""


async def search_multi(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/search/multi",
            params={"api_key": settings.tmdb_api_key, "query": query, "include_adult": "false"},
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
                               limit: int = 20, region: str = "US") -> list[int]:
    """Most popular titles currently on a watch provider (JustWatch data via
    TMDB) — returns TMDB ids, most popular first. No streaming site is touched."""
    ids: list[int] = []
    page = 1
    async with httpx.AsyncClient(timeout=15) as client:
        while len(ids) < limit and page <= 5:
            r = await client.get(
                f"{BASE}/discover/{media_type}",
                params={
                    "api_key": settings.tmdb_api_key,
                    "with_watch_providers": provider_id,
                    "watch_region": region,
                    "sort_by": "popularity.desc",
                    # TMDB popularity is easily gamed by obscure titles; require
                    # a real audience so "top" means recognizable content.
                    "vote_count.gte": 200,
                    "page": page,
                },
            )
            r.raise_for_status()
            data = r.json()
            ids.extend(item["id"] for item in data.get("results", []))
            if page >= data.get("total_pages", 1):
                break
            page += 1
    return ids[:limit]


async def get_details(tmdb_id: int, media_type: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}", params={"api_key": settings.tmdb_api_key}
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
    }
