from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import sites
from db import get_session
from models import Service, Title

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def library(
    request: Request,
    service: str | None = None,
    watched: str | None = None,
    q: str | None = None,
    sort: str = "title",
    session: AsyncSession = Depends(get_session),
):
    query = select(Title).options(selectinload(Title.service)).order_by(Title.added_at.desc())
    if service:
        query = query.join(Service).where(Service.slug == service)
    if watched in ("true", "false"):
        query = query.where(Title.watched == (watched == "true"))
    if q and q.strip():
        query = query.where(Title.title.ilike(f"%{q.strip()}%"))
    titles = (await session.execute(query)).scalars().all()

    # The same title on several services combines into one tile; providers
    # sort alphabetically and the first is the tile's link target (default).
    by_key: dict[tuple, list[Title]] = {}
    for t in titles:
        by_key.setdefault((t.tmdb_id, t.media_type), []).append(t)
    groups = []
    for rows in by_key.values():
        rows = sorted(rows, key=lambda r: r.service.name.lower())
        groups.append({
            "primary": rows[0],
            "services": [r.service for r in rows],
            "watched": any(r.watched for r in rows),
            "added": max(r.added_at for r in rows),
        })
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
    return templates.TemplateResponse(request, "library.html", {
        "groups": groups,
        "services": services,
        "active_service": service,
        "active_watched": watched,
        "q": q,
        "sort": sort,
    })


@router.get("/add")
async def add_page(request: Request, session: AsyncSession = Depends(get_session)):
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "add.html", {"services": services})


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
    siblings = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.tmdb_id == title.tmdb_id, Title.media_type == title.media_type)
    )).scalars().all()
    providers = sorted(siblings, key=lambda r: r.service.name.lower())
    return templates.TemplateResponse(request, "detail.html", {
        "t": title,
        "providers": providers,
        "group_watched": any(r.watched for r in providers),
    })
