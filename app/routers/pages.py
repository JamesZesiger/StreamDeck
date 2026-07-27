import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import prefs
import sites
import tmdb
from db import get_session
from models import (MediaType, Profile, ProfileEpisodeWatch, ProfileListItem,
                    ProfileWatch, Service, Title)
from profiles import (RATING_CAPS, active_profile, allowed_service_slugs,
                      cert_level, settings_locked, title_allowed)

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

# Season/episode lists: airing shows gain episodes, so cache with a TTL.
SEASON_TTL = 6 * 3600
_seasons_cache: dict[tuple, tuple[float, list[dict]]] = {}
_episodes_cache: dict[tuple, tuple[float, list[dict]]] = {}


async def seasons_cached(tmdb_id: int) -> list[dict]:
    key = (tmdb_id, prefs.get_language())
    hit = _seasons_cache.get(key)
    if not hit or time.monotonic() - hit[0] > SEASON_TTL:
        hit = (time.monotonic(), await tmdb.get_seasons(tmdb_id))
        _seasons_cache[key] = hit
    return hit[1]


async def episodes_cached(tmdb_id: int, season_number: int) -> list[dict]:
    key = (tmdb_id, season_number, prefs.get_language())
    hit = _episodes_cache.get(key)
    if not hit or time.monotonic() - hit[0] > SEASON_TTL:
        hit = (time.monotonic(),
               await tmdb.get_season_episodes(tmdb_id, season_number))
        _episodes_cache[key] = hit
    return hit[1]


async def season_context(profile: Profile, tmdb_id: int, season_number: int,
                         session: AsyncSession) -> dict:
    """Context for the episode-list partial — shared with the season-level
    mark endpoint in api.py so both render the same fragment."""
    episodes = await episodes_cached(tmdb_id, season_number)
    watched_eps = set((await session.execute(
        select(ProfileEpisodeWatch.episode).where(
            ProfileEpisodeWatch.profile_id == profile.id,
            ProfileEpisodeWatch.tmdb_id == tmdb_id,
            ProfileEpisodeWatch.season == season_number))).scalars())
    return {
        "episodes": episodes,
        "watched_eps": watched_eps,
        "tmdb_id": tmdb_id,
        "season_number": season_number,
        "all_watched": bool(episodes) and len(watched_eps) >= len(episodes),
    }

# Coming Soon banner: (region, language) -> (built-at, slides). Release
# schedules move slowly; refresh a few times a day.
UPCOMING_TTL = 6 * 3600
_upcoming_cache: dict[tuple, tuple[float, list[dict]]] = {}


async def _upcoming_slides(profile: Profile) -> list[dict]:
    """Best-effort Coming Soon slides. Kid profiles with a rating cap get
    none — unreleased titles have no certification yet, and the cap policy
    hides unrated content."""
    if profile.max_rating_level is not None:
        return []
    key = (prefs.get_region(), prefs.get_language())
    hit = _upcoming_cache.get(key)
    if hit and time.monotonic() - hit[0] < UPCOMING_TTL:
        return hit[1]
    try:
        slides = await tmdb.get_upcoming()
    except Exception:
        return []
    for s in slides:
        when = datetime.strptime(s["release_date"], "%Y-%m-%d")
        s["date_label"] = when.strftime("%b %d").replace(" 0", " ")
    _upcoming_cache[key] = (time.monotonic(), slides)
    return slides


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
    ep_by_show: dict[int, list[ProfileEpisodeWatch]] = {}
    for r in (await session.execute(
            select(ProfileEpisodeWatch)
            .where(ProfileEpisodeWatch.profile_id == profile.id))).scalars():
        ep_by_show.setdefault(r.tmdb_id, []).append(r)

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
            # Every provider dropped it (availability refresh flags rows).
            "unavailable": all(r.unavailable_since for r in rows),
            "unavailable_at": max((r.unavailable_since for r in rows
                                   if r.unavailable_since), default=None),
        })
        # TV episode progress: chip shows the furthest-watched episode.
        eps = ep_by_show.get(key[0]) if key[1] == MediaType.tv else None
        latest = max(eps, key=lambda r: (r.season, r.episode)) if eps else None
        groups[-1]["ep_label"] = f"S{latest.season} · E{latest.episode}" if latest else None
        groups[-1]["ep_last_at"] = max(r.watched_at for r in eps) if eps else None
    # "Recently left": groups every service dropped in the last 30 days,
    # newest departures first — feeds the library's leaving banner.
    # Shows mid-watch (episode activity, not marked fully watched), most
    # recently watched first — feeds the Continue Watching strip.
    continuing = sorted(
        (g for g in groups if g["ep_label"] and not g["watched"]),
        key=lambda g: g["ep_last_at"], reverse=True)[:8]
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    leaving = sorted(
        (g for g in groups
         if g["unavailable"] and g["unavailable_at"] and g["unavailable_at"] >= cutoff),
        key=lambda g: g["unavailable_at"], reverse=True)[:8]
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
        "upcoming": await _upcoming_slides(profile),
        "leaving": leaving,
        "continuing": continuing,
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


# Discover: TMDB recommendations seeded by the profile's recent watches
# (popular-on-your-services when there's no history yet), filtered to titles
# your configured providers actually stream in the chosen region and that
# aren't in the library. Building a page costs ~60 TMDB detail calls, so
# results are cached per profile for a while; Refresh busts the cache.
DISCOVER_TTL = 1800          # seconds a built page stays cached
DISCOVER_SEEDS = 8           # recent watches used as recommendation seeds
DISCOVER_CANDIDATES = 60     # candidates detail-fetched per build
DISCOVER_RESULTS = 24        # cards shown
# (profile id, region, language) -> (built-at, cards, seed titles)
_discover_cache: dict[tuple, tuple[float, list[dict], list[str]]] = {}


async def _build_discover(profile: Profile, region: str,
                          session: AsyncSession) -> tuple[list[dict], list[str]]:
    allowed = allowed_service_slugs(profile)
    site_by_slug = {s["slug"]: s for s in sites.load_sites()}
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    # Only sites with a TMDB provider id can be matched against availability.
    provider_services = [
        (site_by_slug[s.slug]["tmdb_provider_id"], s) for s in services
        if (allowed is None or s.slug in allowed)
        and site_by_slug.get(s.slug, {}).get("tmdb_provider_id")]
    if not provider_services:
        return [], []

    watched = (await session.execute(
        select(ProfileWatch).where(ProfileWatch.profile_id == profile.id)
        .order_by(ProfileWatch.watched_at.desc()))).scalars().all()
    watched_keys = {(w.tmdb_id, w.media_type.value) for w in watched}
    library_keys = {(tid, mt.value) for tid, mt in (await session.execute(
        select(Title.tmdb_id, Title.media_type))).all()}
    seeds = [(w.tmdb_id, w.media_type.value) for w in watched[:DISCOVER_SEEDS]]

    seed_titles: list[str] = []
    if seeds:
        name_by_key = {(tid, mt.value): name for tid, mt, name in (
            await session.execute(
                select(Title.tmdb_id, Title.media_type, Title.title))).all()}
        for k in seeds:
            name = name_by_key.get(k)
            if name and name not in seed_titles:
                seed_titles.append(name)

    # Candidate keys scored by (how many seeds/providers surfaced it, best
    # popularity seen). counts[key] = [hits, popularity].
    counts: dict[tuple, list] = {}

    def tally(key: tuple, popularity: float) -> None:
        if key in library_keys or key in watched_keys:
            return
        entry = counts.setdefault(key, [0, 0.0])
        entry[0] += 1
        entry[1] = max(entry[1], popularity)

    if seeds:
        batches = await asyncio.gather(
            *(tmdb.get_recommendations(tid, mt) for tid, mt in seeds),
            return_exceptions=True)
        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for item in batch:
                tally((item["tmdb_id"], item["media_type"]), item["popularity"])
    else:
        # Cold start: what's popular on each of your services right now.
        pairs = [(pid, mt) for pid, _ in provider_services
                 for mt in ("movie", "tv")]
        batches = await asyncio.gather(
            *(tmdb.discover_by_provider(pid, mt, limit=15, min_votes=500)
              for pid, mt in pairs),
            return_exceptions=True)
        for (_, mt), batch in zip(pairs, batches):
            if isinstance(batch, BaseException):
                continue
            for rank, tid in enumerate(batch):
                tally((tid, mt), float(len(batch) - rank))

    ranked = sorted(counts, key=lambda k: (counts[k][0], counts[k][1]),
                    reverse=True)[:DISCOVER_CANDIDATES]

    sem = asyncio.Semaphore(8)

    async def fetch(tid: int, mt: str) -> dict | None:
        async with sem:
            try:
                return await tmdb.get_details(tid, mt)
            except Exception:
                return None

    details = await asyncio.gather(*(fetch(tid, mt) for tid, mt in ranked))
    cards: list[dict] = []
    for d in details:
        if not d:
            continue
        # Same content policy the library applies to kid profiles.
        if profile.max_rating_level is not None:
            if d["mature"] and profile.max_rating_level < 3:
                continue
            level = cert_level(d["certification"])
            if level is None or level > profile.max_rating_level:
                continue
        matches = []
        for pid, service in provider_services:
            offered = (pid in d["provider_regions"].get(region, set()) if region
                       else any(pid in ids
                                for ids in d["provider_regions"].values()))
            if offered:
                matches.append(service)
        if not matches:
            continue
        cards.append({
            "tmdb_id": d["tmdb_id"],
            "media_type": d["media_type"],
            "title": d["title"],
            "poster_url": d["poster_url"],
            "year": d["release_year"],
            "rating": d["rating"],
            "overview": d["overview"],
            "services": [{"id": s.id, "name": s.name, "icon_path": s.icon_path}
                         for s in matches],
        })
        if len(cards) >= DISCOVER_RESULTS:
            break
    return cards, seed_titles


@router.get("/discover")
async def discover(request: Request, refresh: str | None = None,
                   session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    region = prefs.get_region()
    key = (profile.id, region, prefs.get_language())
    cached = _discover_cache.get(key)
    if cached and not refresh and time.monotonic() - cached[0] < DISCOVER_TTL:
        cards, seed_titles = cached[1], cached[2]
    else:
        cards, seed_titles = await _build_discover(profile, region, session)
        _discover_cache[key] = (time.monotonic(), cards, seed_titles)
    return templates.TemplateResponse(request, "discover.html", {
        "cards": cards,
        "seed_titles": seed_titles,
        "active_profile": profile,
    })


@router.get("/manifest.json")
async def manifest():
    """PWA manifest at the root so its scope ("/") covers the whole app."""
    return FileResponse("static/manifest.json",
                        media_type="application/manifest+json")


@router.get("/profiles/menu")
async def profiles_menu(request: Request, session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    profiles = (await session.execute(
        select(Profile).order_by(Profile.id))).scalars().all()
    watched_count = (await session.execute(
        select(func.count()).select_from(ProfileWatch)
        .where(ProfileWatch.profile_id == profile.id))).scalar_one()
    list_count = (await session.execute(
        select(func.count()).select_from(ProfileListItem)
        .where(ProfileListItem.profile_id == profile.id))).scalar_one()
    return templates.TemplateResponse(request, "partials/profile_menu.html", {
        "profiles": profiles,
        "active_profile": profile,
        "locked": settings_locked(profile, request),
        "watched_count": watched_count,
        "list_count": list_count,
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

    # TV: seasons + this profile's episode progress. Best-effort — no
    # seasons (TMDB down / none listed) just hides the episode tracker.
    seasons, watched_by_season, ep_progress = [], {}, None
    if title.media_type == MediaType.tv:
        try:
            seasons = await seasons_cached(title.tmdb_id)
        except Exception:
            seasons = []
        if seasons:
            ep_watched = {(r.season, r.episode) for r in (await session.execute(
                select(ProfileEpisodeWatch).where(
                    ProfileEpisodeWatch.profile_id == profile.id,
                    ProfileEpisodeWatch.tmdb_id == title.tmdb_id))).scalars()}
            for s, _ in ep_watched:
                watched_by_season[s] = watched_by_season.get(s, 0) + 1
            next_up = next(
                ((s["season_number"], e) for s in seasons
                 for e in range(1, s["episode_count"] + 1)
                 if (s["season_number"], e) not in ep_watched), None)
            ep_progress = {
                "watched": len(ep_watched),
                "total": sum(s["episode_count"] for s in seasons),
                "next_up": next_up,
            }

    return templates.TemplateResponse(request, "detail.html", {
        "t": title,
        "providers": providers,
        "group_watched": watch is not None,
        "watched_at": watch.watched_at if watch else None,
        "in_list": in_list,
        "trailer": await _get_trailer(title),
        "seasons": seasons,
        "watched_by_season": watched_by_season,
        "ep_progress": ep_progress,
        "active_profile": profile,
    })


@router.get("/titles/{title_id}/episodes/{season_number}")
async def season_episodes(request: Request, title_id: int, season_number: int,
                          session: AsyncSession = Depends(get_session)):
    """htmx partial: one season's episode list, loaded when its accordion
    opens on the detail page."""
    title = await session.get(Title, title_id)
    if not title or title.media_type != MediaType.tv:
        raise HTTPException(404)
    profile = await active_profile(request, session)
    ctx = await season_context(profile, title.tmdb_id, season_number, session)
    return templates.TemplateResponse(request, "partials/episode_list.html", ctx)


# (tmdb id, media type, language) -> {key, name} or None ("no trailer").
# Failed lookups aren't cached, so a TMDB blip retries on the next view.
_trailer_cache: dict[tuple, dict | None] = {}


async def _get_trailer(title: Title) -> dict | None:
    key = (title.tmdb_id, title.media_type.value, prefs.get_language())
    if key not in _trailer_cache:
        try:
            _trailer_cache[key] = await tmdb.get_trailer(
                title.tmdb_id, title.media_type.value)
        except Exception:
            return None
    return _trailer_cache[key]
