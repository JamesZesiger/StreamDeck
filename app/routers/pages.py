from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import sites
from db import get_session
from models import (MediaType, Profile, ProfileListItem, ProfileWatch, Service,
                    Title)
from profiles import active_profile

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
    sort: str = "title",
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
    query = select(Title).options(selectinload(Title.service)).order_by(Title.added_at.desc())
    if profile.hide_mature:
        query = query.where(Title.mature.is_(False))
    if service:
        query = query.join(Service).where(Service.slug == service)
    if media_type in ("movie", "tv"):
        query = query.where(Title.media_type == MediaType(media_type))
    if decade_int:
        query = query.where(Title.release_year >= decade_int,
                            Title.release_year < decade_int + 10)
    if q and q.strip():
        query = query.where(Title.title.ilike(f"%{q.strip()}%"))
    titles = (await session.execute(query)).scalars().all()
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
        groups.append({
            "primary": rows[0],
            "services": [r.service for r in rows],
            "watched": key in watched_keys,
            "in_list": key in list_keys,
            "added": max(r.added_at for r in rows),
        })
    if watched in ("true", "false"):
        groups = [g for g in groups if g["watched"] == (watched == "true")]
    if list_only == "true":
        groups = [g for g in groups if g["in_list"]]
    # Stable sorts: the later sort is the primary key, the earlier the tiebreak.
    if sort == "added":
        groups.sort(key=lambda g: g["primary"].title.lower())
        groups.sort(key=lambda g: g["added"], reverse=True)
    else:  # default: alphabetical first, date second
        groups.sort(key=lambda g: g["added"], reverse=True)
        groups.sort(key=lambda g: g["primary"].title.lower())

    # htmx search requests swap only the grid
    if request.headers.get("hx-request") == "true":
        return templates.TemplateResponse(request, "partials/tile_grid.html",
                                          {"groups": groups, "q": q})

    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    # Genre / decade choices come from the whole library, not the filtered
    # view, so options don't disappear as filters narrow the list.
    all_rows = (await session.execute(select(Title.genres, Title.release_year))).all()
    genres = sorted({g.strip() for gs, _ in all_rows for g in gs.split(",") if g.strip()})
    decades = sorted({(y // 10) * 10 for _, y in all_rows if y}, reverse=True)
    return templates.TemplateResponse(request, "library.html", {
        "groups": groups,
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
    profiles = (await session.execute(
        select(Profile).order_by(Profile.id))).scalars().all()
    return templates.TemplateResponse(request, "partials/profile_menu.html", {
        "profiles": profiles,
        "active_profile": await active_profile(request, session),
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
    title_counts = dict((await session.execute(
        select(Service.slug, func.count(Title.id))
        .outerjoin(Title).group_by(Service.slug)
    )).all())
    site_rows = [{
        "name": s["name"],
        "slug": s["slug"],
        "base_domain": s["base_domain"],
        "icon_path": s["icon_path"],
        "username": s.get("username", ""),
        "password_set": bool(s.get("password")),
        "title_count": title_counts.get(s["slug"], 0),
        "tmdb_provider_id": s.get("tmdb_provider_id"),
        "search_url": s.get("search_url", ""),
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
    if profile.hide_mature and title.mature:
        raise HTTPException(404, "Title not found")
    siblings = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.tmdb_id == title.tmdb_id, Title.media_type == title.media_type)
    )).scalars().all()
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
