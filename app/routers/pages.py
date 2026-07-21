from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import neko_client
from config import service_credentials, settings
from db import get_session
from models import PlaybackMode, Service, Title

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def library(
    request: Request,
    service: str | None = None,
    watched: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Title).options(selectinload(Title.service)).order_by(Title.added_at.desc())
    if service:
        query = query.join(Service).where(Service.slug == service)
    if watched in ("true", "false"):
        query = query.where(Title.watched == (watched == "true"))
    titles = (await session.execute(query)).scalars().all()
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "library.html", {
        "titles": titles,
        "services": services,
        "active_service": service,
        "active_watched": watched,
    })


@router.get("/add")
async def add_page(request: Request, session: AsyncSession = Depends(get_session)):
    services = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "add.html", {"services": services})


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
        "has_credentials": service_credentials(title.service.slug) is not None,
    })
