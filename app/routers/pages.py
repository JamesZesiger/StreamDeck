import asyncio
import random

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import prefs
import sites
import tmdb
from db import get_session
from models import (MediaType, Profile, ProfileListItem, ProfileWatch, Service,
                    Title)
from profiles import (RATING_CAPS, active_profile, allowed_service_slugs,
                      settings_locked, title_allowed)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
# Toolbar language and region pickers (base.html) render on every page.
templates.env.globals["languages"] = prefs.LANGUAGES
templates.env.globals["current_language"] = prefs.get_language
templates.env.globals["regions"] = prefs.REGIONS
templates.env.globals["current_region"] = prefs.get_region
templates.env.globals["accents"] = prefs.ACCENTS
templates.env.globals["current_theme"] = prefs.get_theme

# Collection details never really change; fetch each id from TMDB once.
_collection_cache: dict[int, dict] = {}


async def _random_collections(n: int = 5) -> list[dict]:
    """n random curated TMDB collections for the carousel. Best-effort:
    failed fetches are skipped, so this returns [] if TMDB is unreachable."""
    ids = random.sample(tmdb.CURATED_COLLECTIONS,
                        min(n, len(tmdb.CURATED_COLLECTIONS)))

    async def fetch(cid: int) -> dict | None:
        if cid not in _collection_cache:
            try:
                _collection_cache[cid] = await tmdb.get_collection(cid)
            except Exception:
                return None
        return _collection_cache[cid]

    return [c for c in await asyncio.gather(*(fetch(i) for i in ids)) if c]


@router.get("/")
async def library(
    request: Request,
    service: str | None = None,
    watched: str | None = None,
    media_type: str | None = Query(None, alias="type"),
    genre: str | None = None,
    decade: str | None = None,
    list_only: str | None = Query(None, alias="list"),
    q: str | None = None,
    sort: str = "rating",
    session: AsyncSession = Depends(get_session),
):
    profile = await active_profile(request, session)
    watched_keys = {tuple(row) for row in (await session.execute(
        select(ProfileWatch.tmdb_id, ProfileWatch.media_type)
        .where(ProfileWatch.profile_id == profile.id))).all()}
    list_keys = {tuple(row) for row in (await session.execute(
        select(ProfileListItem.tmdb_id, ProfileListItem.media_type)
        .where(ProfileListItem.profile_id == profile.id))).all()}

    decade_int = int(decade) if decade and decade.isdigit() else None
    allowed = allowed_service_slugs(profile)
    query = select(Title).options(selectinload(Title.service)).order_by(Title.added_at.desc())
    if service or allowed is not None:
        query = query.join(Service)
        if allowed is not None:
            query = query.where(Service.slug.in_(allowed))
        if service:
            query = query.where(Service.slug == service)
    if media_type in ("movie", "tv"):
        query = query.where(Title.media_type == MediaType(media_type))
    if decade_int:
        query = query.where(Title.release_year >= decade_int,
                            Title.release_year < decade_int + 10)
    if q and q.strip():
        query = query.where(Title.title.ilike(f"%{q.strip()}%"))
    titles = (await session.execute(query)).scalars().all()
    if profile.max_rating_level is not None:
        titles = [t for t in titles if title_allowed(profile, t)]
    # Region pref: only titles watchable there. Titles with no availability
    # data (custom sites, TMDB gaps) stay visible — unknown isn't unavailable.
    region = prefs.get_region()
    if region:
        titles = [t for t in titles
                  if not t.regions
                  or region in (r.strip() for r in t.regions.split(","))]
    if genre:
        # Exact match on the comma-separated list, so "Action" doesn't also
        # match "Action & Adventure".
        titles = [t for t in titles
                  if genre in (g.strip() for g in t.genres.split(","))]

    # The same title on several services combines into one tile; providers
    # sort alphabetically and the first is the tile's link target (default).
    by_key: dict[tuple, list[Title]] = {}
    for t in titles:
        by_key.setdefault((t.tmdb_id, t.media_type), []).append(t)
    groups = []
    for key, rows in by_key.items():
        rows = sorted(rows, key=lambda r: r.service.name.lower())
        # Provider rows hold the same TMDB title fetched at different times;
        # the one with the most votes is the freshest stats snapshot.
        stats = max(rows, key=lambda r: r.vote_count or 0)
        groups.append({
            "primary": rows[0],
            "services": [r.service for r in rows],
            "watched": key in watched_keys,
            "in_list": key in list_keys,
            "added": max(r.added_at for r in rows),
            "raw_rating": stats.rating or 0,
            "votes": stats.vote_count or 0,
        })
    # "Highest rated" uses a Bayesian (IMDb-style) weighted rating, not the
    # raw TMDB average: WR = v/(v+m)*R + m/(v+m)*C. A 9.4 backed by a few
    # hundred votes shouldn't outrank an 8.9 backed by tens of thousands, so
    # each average is pulled toward the library mean C until enough votes
    # (m) back it up. Unrated titles stay at 0 and sink to the bottom.
    prior_votes = 500  # m: votes needed before R outweighs the prior C
    rated = [g for g in groups if g["raw_rating"] and g["votes"]]
    mean = sum(g["raw_rating"] for g in rated) / len(rated) if rated else 0
    for g in groups:
        v, r = g["votes"], g["raw_rating"]
        g["rating"] = ((v * r + prior_votes * mean) / (v + prior_votes)
                       if v and r else 0)
    if watched in ("true", "false"):
        groups = [g for g in groups if g["watched"] == (watched == "true")]
    if list_only == "true":
        groups = [g for g in groups if g["in_list"]]
    # Stable sorts: the later sort is the primary key, the earlier the tiebreak.
    if sort == "added":
        groups.sort(key=lambda g: g["primary"].title.lower())
        groups.sort(key=lambda g: g["added"], reverse=True)
    elif sort == "title":
        groups.sort(key=lambda g: g["added"], reverse=True)
        groups.sort(key=lambda g: g["primary"].title.lower())
    elif sort == "popularity":
        # "Most popular" = lifetime vote count. TMDB's popularity score is a
        # trending-this-week metric frozen at import time, so it ranks
        # whatever was hot the day a title was fetched; vote count is
        # cumulative, stable, and comparable across import dates.
        groups.sort(key=lambda g: g["rating"], reverse=True)
        groups.sort(key=lambda g: g["votes"], reverse=True)
    elif sort == "year":
        groups.sort(key=lambda g: g["rating"], reverse=True)
        groups.sort(key=lambda g: g["primary"].release_year or 0, reverse=True)
    else:  # default "rating": weighted rating first, vote count breaks ties
        groups.sort(key=lambda g: g["votes"], reverse=True)
        groups.sort(key=lambda g: g["rating"], reverse=True)

    # htmx search requests swap only the grid
    if request.headers.get("hx-request") == "true":
        return templates.TemplateResponse(request, "partials/tile_grid.html",
                                          {"groups": groups, "q": q})

    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    if allowed is not None:
        services = [s for s in services if s.slug in allowed]
    # Genre / decade choices come from the whole library, not the filtered
    # view, so options don't disappear as filters narrow the list.
    all_rows = (await session.execute(select(Title.genres, Title.release_year))).all()
    genres = sorted({g.strip() for gs, _ in all_rows for g in gs.split(",") if g.strip()})
    decades = sorted({(y // 10) * 10 for _, y in all_rows if y}, reverse=True)
    return templates.TemplateResponse(request, "library.html", {
        "groups": groups,
        "collections": await _random_collections(),
        "services": services,
        "genres": genres,
        "decades": decades,
        "active_service": service,
        "active_watched": watched,
        "active_type": media_type,
        "active_genre": genre,
        "active_decade": decade_int,
        "active_list": list_only,
        "active_profile": profile,
        "q": q,
        "sort": sort,
    })


@router.get("/profiles/menu")
async def profiles_menu(request: Request, session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    profiles = (await session.execute(
        select(Profile).order_by(Profile.id))).scalars().all()
    return templates.TemplateResponse(request, "partials/profile_menu.html", {
        "profiles": profiles,
        "active_profile": profile,
        "locked": settings_locked(profile, request),
    })


@router.get("/settings")
async def settings_page(request: Request, session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    if settings_locked(profile, request):
        return templates.TemplateResponse(request, "pin_gate.html", {
            "active_profile": profile,
            "gate_action": "change settings",
        })
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "settings.html", {
        "active_profile": profile,
        "services": services,
        "allowed": allowed_service_slugs(profile),
        "rating_caps": RATING_CAPS,
        "pin_set": bool(prefs.get_pin_hash()),
    })


@router.get("/add")
async def add_page(request: Request, session: AsyncSession = Depends(get_session)):
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "add.html", {
        "services": services,
        "active_profile": await active_profile(request, session),
    })


@router.get("/sites")
async def sites_page(request: Request, msg: str | None = None, add: str | None = None,
                     session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    if settings_locked(profile, request):
        # Site management stays behind the parent PIN while a kid-mode
        # profile is active.
        return templates.TemplateResponse(request, "pin_gate.html", {
            "active_profile": profile,
            "gate_action": "manage sites",
        })
    title_counts = dict((await session.execute(
        select(Service.slug, func.count(Title.id))
        .outerjoin(Title).group_by(Service.slug)
    )).all())
    site_rows = [{
        "name": s["name"],
        "slug": s["slug"],
        "base_domain": s["base_domain"],
        "icon_path": s["icon_path"],
        "title_count": title_counts.get(s["slug"], 0),
        "tmdb_provider_id": s.get("tmdb_provider_id"),
        "search_url": s.get("search_url", ""),
        "search_links_only": s.get("search_links_only", False),
    } for s in sites.load_sites()]
    return templates.TemplateResponse(request, "sites.html", {
        "sites": site_rows, "msg": msg, "show_add": bool(add),
        "active_profile": await active_profile(request, session),
    })


@router.get("/icons/{slug}.svg")
async def site_icon(slug: str):
    site = sites.get_site(slug)
    if not site:
        raise HTTPException(404)
    return Response(content=sites.icon_svg(site["slug"], site["name"]),
                    media_type="image/svg+xml")


async def _get_title(title_id: int, session: AsyncSession) -> Title:
    title = (await session.execute(
        select(Title).options(selectinload(Title.service)).where(Title.id == title_id)
    )).scalar_one_or_none()
    if not title:
        raise HTTPException(404, "Title not found")
    return title


@router.get("/titles/{title_id}")
async def detail(request: Request, title_id: int, session: AsyncSession = Depends(get_session)):
    title = await _get_title(title_id, session)
    profile = await active_profile(request, session)
    if not title_allowed(profile, title):
        raise HTTPException(404, "Title not found")
    siblings = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.tmdb_id == title.tmdb_id, Title.media_type == title.media_type)
    )).scalars().all()
    allowed = allowed_service_slugs(profile)
    if allowed is not None:
        siblings = [s for s in siblings if s.service.slug in allowed]
        if not siblings:
            raise HTTPException(404, "Title not found")
    providers = sorted(siblings, key=lambda r: r.service.name.lower())
    watch = (await session.execute(
        select(ProfileWatch).where(ProfileWatch.profile_id == profile.id,
                                   ProfileWatch.tmdb_id == title.tmdb_id,
                                   ProfileWatch.media_type == title.media_type)
    )).scalar_one_or_none()
    in_list = (await session.execute(
        select(ProfileListItem).where(ProfileListItem.profile_id == profile.id,
                                      ProfileListItem.tmdb_id == title.tmdb_id,
                                      ProfileListItem.media_type == title.media_type)
    )).scalar_one_or_none() is not None
    return templates.TemplateResponse(request, "detail.html", {
        "t": title,
        "providers": providers,
        "group_watched": watch is not None,
        "watched_at": watch.watched_at if watch else None,
        "in_list": in_list,
        "active_profile": profile,
    })
