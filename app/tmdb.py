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
    }
