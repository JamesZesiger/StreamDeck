from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import neko_client
import sites
from config import settings
from db import get_session
from models import PlaybackMode, Service, Title

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def library(
    request: Request,
    service: str | None = None,
    watched: str | None = None,
    q: str | None = None,
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

    # htmx search requests swap only the grid
    if request.headers.get("hx-request") == "true":
        return templates.TemplateResponse(request, "partials/tile_grid.html",
                                          {"titles": titles, "q": q})

    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "library.html", {
        "titles": titles,
        "services": services,
        "active_service": service,
        "active_watched": watched,
        "q": q,
    })


@router.get("/add")
async def add_page(request: Request, session: AsyncSession = Depends(get_session)):
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "add.html", {"services": services})


@router.get("/sites")
async def sites_page(request: Request, msg: str | None = None,
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
        "playback_mode": s["playback_mode"],
        "username": s.get("username", ""),
        "password_set": bool(s.get("password")),
        "title_count": title_counts.get(s["slug"], 0),
        "tmdb_provider_id": s.get("tmdb_provider_id"),
    } for s in sites.load_sites()]
    return templates.TemplateResponse(request, "sites.html", {"sites": site_rows, "msg": msg})


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
    return templates.TemplateResponse(request, "detail.html", {
        "t": title,
        "embedded": title.service.playback_mode == PlaybackMode.embedded,
    })


@router.get("/titles/{title_id}/play")
async def play(request: Request, title_id: int, session: AsyncSession = Depends(get_session)):
    title = await _get_title(title_id, session)
    if title.service.playback_mode != PlaybackMode.embedded:
        raise HTTPException(400, "This service uses deep-link playback")

    navigated = await neko_client.navigate(title.deep_link)
    title.last_played_at = datetime.now(timezone.utc)
    await session.commit()

    return templates.TemplateResponse(request, "player.html", {
        "t": title,
        "navigated": navigated,
        "neko_url": settings.neko_public_url,
        "neko_password": settings.neko_user_password,
        "has_credentials": sites.get_credentials(title.service.slug) is not None,
    })
