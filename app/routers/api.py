import html

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import sites
import tmdb
from db import get_session
from models import MediaType, PlaybackMode, Service, Title

router = APIRouter(prefix="/api")
templates = Jinja2Templates(directory="templates")


@router.post("/resolve-url")
async def resolve_url(
    request: Request,
    url: str = Form(...),
    query: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    slug = sites.detect_service_slug(url)
    service = None
    if slug:
        service = (await session.execute(
            select(Service).where(Service.slug == slug)
        )).scalar_one_or_none()
    results = await tmdb.search_multi(query) if query.strip() else []
    return templates.TemplateResponse(request, "partials/search_results.html", {
        "results": results,
        "service": service,
        "url": url,
    })


@router.post("/titles")
async def create_title(
    request: Request,
    url: str = Form(...),
    service_id: int = Form(...),
    tmdb_id: int = Form(...),
    media_type: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    service = await session.get(Service, service_id)
    if not service:
        raise HTTPException(400, "Unknown service")
    details = await tmdb.get_details(tmdb_id, media_type)
    title = Title(
        service_id=service.id,
        tmdb_id=details["tmdb_id"],
        media_type=MediaType(details["media_type"]),
        title=details["title"],
        overview=details["overview"],
        poster_url=details["poster_url"],
        backdrop_url=details["backdrop_url"],
        runtime_minutes=details["runtime_minutes"],
        release_year=details["release_year"],
        deep_link=url,
    )
    session.add(title)
    await session.commit()
    return Response(headers={"HX-Redirect": f"/titles/{title.id}"})


@router.patch("/titles/{title_id}/watched")
async def toggle_watched(title_id: int, session: AsyncSession = Depends(get_session)):
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(404)
    title.watched = not title.watched
    await session.commit()
    label = "Watched ✓" if title.watched else "Mark watched"
    return Response(content=label, media_type="text/plain")


@router.delete("/titles/{title_id}")
async def delete_title(title_id: int, session: AsyncSession = Depends(get_session)):
    title = await session.get(Title, title_id)
    if title:
        await session.delete(title)
        await session.commit()
    return Response(headers={"HX-Redirect": "/"})


@router.get("/credentials/{slug}")
async def credentials(request: Request, slug: str):
    creds = sites.get_credentials(slug)
    if not creds:
        raise HTTPException(404, "No credentials configured for this service")
    return templates.TemplateResponse(request, "partials/credentials.html", {"creds": creds})


@router.post("/sites")
async def create_site(
    name: str = Form(...),
    base_domain: str = Form(...),
    playback_mode: str = Form("embedded"),
    username: str = Form(""),
    password: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if playback_mode not in ("embedded", "deeplink"):
        playback_mode = "embedded"
    try:
        site = sites.add_site(name, base_domain, playback_mode, username, password)
    except ValueError as exc:
        return Response(
            content=f'<p class="text-sm text-amber-400">{html.escape(str(exc))}</p>',
            media_type="text/html",
        )
    session.add(Service(
        name=site["name"],
        slug=site["slug"],
        base_domain=site["base_domain"],
        icon_path=site["icon_path"],
        playback_mode=PlaybackMode(site["playback_mode"]),
    ))
    await session.commit()
    return Response(headers={"HX-Redirect": "/sites"})
