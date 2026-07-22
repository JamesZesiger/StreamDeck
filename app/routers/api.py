import asyncio
import html
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import sites
import tmdb
from db import get_session
from models import (MediaType, Profile, ProfileListItem, ProfileWatch, Service,
                    Title)
from profiles import active_profile, set_profile_cookie

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
        genres=details["genres"],
        deep_link=url,
    )
    session.add(title)
    await session.commit()
    return Response(headers={"HX-Redirect": f"/titles/{title.id}"})


@router.patch("/titles/{title_id}/watched")
async def toggle_watched(request: Request, title_id: int,
                         session: AsyncSession = Depends(get_session)):
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(404)
    # Watched state applies to the combined title, across all its providers,
    # and belongs to the active profile only.
    profile = await active_profile(request, session)
    watch = (await session.execute(
        select(ProfileWatch).where(ProfileWatch.profile_id == profile.id,
                                   ProfileWatch.tmdb_id == title.tmdb_id,
                                   ProfileWatch.media_type == title.media_type)
    )).scalar_one_or_none()
    if watch:
        await session.delete(watch)
        label = "Mark watched"
    else:
        session.add(ProfileWatch(profile_id=profile.id, tmdb_id=title.tmdb_id,
                                 media_type=title.media_type))
        label = "Watched ✓"
    await session.commit()
    return Response(content=label, media_type="text/plain")


@router.patch("/titles/{title_id}/list")
async def toggle_list(request: Request, title_id: int,
                      session: AsyncSession = Depends(get_session)):
    title = await session.get(Title, title_id)
    if not title:
        raise HTTPException(404)
    profile = await active_profile(request, session)
    item = (await session.execute(
        select(ProfileListItem).where(ProfileListItem.profile_id == profile.id,
                                      ProfileListItem.tmdb_id == title.tmdb_id,
                                      ProfileListItem.media_type == title.media_type)
    )).scalar_one_or_none()
    if item:
        await session.delete(item)
        label = "+ My list"
    else:
        session.add(ProfileListItem(profile_id=profile.id, tmdb_id=title.tmdb_id,
                                    media_type=title.media_type))
        label = "In my list ✓"
    await session.commit()
    return Response(content=label, media_type="text/plain")


@router.post("/profiles")
async def create_profile(name: str = Form(...),
                         session: AsyncSession = Depends(get_session)):
    name = name.strip()[:50]
    if not name:
        return _msg("Profile name required.")
    exists = (await session.execute(
        select(Profile).where(func.lower(Profile.name) == name.lower())
    )).scalar_one_or_none()
    if exists:
        return _msg("A profile with that name already exists.")
    profile = Profile(name=name)
    session.add(profile)
    await session.commit()
    response = Response(headers={"HX-Refresh": "true"})
    set_profile_cookie(response, profile.id)
    return response


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int,
                           session: AsyncSession = Depends(get_session)):
    if not await session.get(Profile, profile_id):
        raise HTTPException(404, "Unknown profile")
    response = Response(headers={"HX-Refresh": "true"})
    set_profile_cookie(response, profile_id)
    return response


@router.delete("/profiles/{profile_id}")
async def delete_profile(request: Request, profile_id: int,
                         session: AsyncSession = Depends(get_session)):
    profiles = (await session.execute(
        select(Profile).order_by(Profile.id))).scalars().all()
    if len(profiles) <= 1:
        return _msg("Can't delete the last profile.")
    profile = next((p for p in profiles if p.id == profile_id), None)
    if not profile:
        raise HTTPException(404, "Unknown profile")
    await session.delete(profile)  # watches/list rows cascade
    await session.commit()
    response = Response(headers={"HX-Refresh": "true"})
    if request.cookies.get("profile_id") == str(profile_id):
        remaining = next(p for p in profiles if p.id != profile_id)
        set_profile_cookie(response, remaining.id)
    return response


@router.delete("/titles/{title_id}")
async def delete_title(title_id: int, session: AsyncSession = Depends(get_session)):
    title = await session.get(Title, title_id)
    if title:
        # Remove the combined title: every provider's row.
        await session.execute(delete(Title).where(
            Title.tmdb_id == title.tmdb_id, Title.media_type == title.media_type))
        await session.commit()
    return Response(headers={"HX-Redirect": "/"})


@router.get("/credentials/{slug}")
async def credentials(request: Request, slug: str):
    creds = sites.get_credentials(slug)
    if not creds:
        raise HTTPException(404, "No credentials configured for this service")
    return templates.TemplateResponse(request, "partials/credentials.html", {"creds": creds})


def _msg(text: str, tone: str = "amber") -> Response:
    return Response(
        content=f'<p class="text-sm text-{tone}-400">{html.escape(text)}</p>',
        media_type="text/html",
    )


@router.post("/sites")
async def create_site(
    name: str = Form(...),
    base_domain: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    tmdb_provider_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    provider_id = int(tmdb_provider_id) if tmdb_provider_id.strip().isdigit() else None
    try:
        site = sites.add_site(name, base_domain, username, password,
                              tmdb_provider_id=provider_id)
    except ValueError as exc:
        return _msg(str(exc))
    session.add(Service(
        name=site["name"],
        slug=site["slug"],
        base_domain=site["base_domain"],
        icon_path=site["icon_path"],
    ))
    await session.commit()
    return Response(headers={"HX-Redirect": "/sites"})


@router.post("/sites/{slug}/edit")
async def edit_site(
    slug: str,
    name: str = Form(...),
    base_domain: str = Form(...),
    tmdb_provider_id: str = Form(""),
    search_url: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    provider_id = int(tmdb_provider_id) if tmdb_provider_id.strip().isdigit() else None
    try:
        site = sites.update_site(slug, name, base_domain,
                                 provider_id, search_url, username, password)
    except ValueError as exc:
        return _msg(str(exc))
    service = (await session.execute(
        select(Service).where(Service.slug == slug)
    )).scalar_one_or_none()
    if service:
        service.name = site["name"]
        service.base_domain = site["base_domain"]
        await session.commit()
    saved_msg = quote(f"Saved {site['name']}.")
    return Response(headers={"HX-Redirect": f"/sites?msg={saved_msg}"})


@router.delete("/sites/{slug}/titles")
async def remove_all_titles(slug: str, session: AsyncSession = Depends(get_session)):
    service = (await session.execute(
        select(Service).where(Service.slug == slug)
    )).scalar_one_or_none()
    if not service:
        raise HTTPException(404, "Unknown site")
    result = await session.execute(delete(Title).where(Title.service_id == service.id))
    await session.commit()
    msg = f"Removed {result.rowcount} title{'' if result.rowcount == 1 else 's'} from {service.name}."
    return Response(headers={"HX-Redirect": f"/sites?msg={quote(msg)}"})


PRELOAD_PER_TYPE = 20  # top-N movies + top-N shows per click


@router.post("/sites/{slug}/preload")
async def preload_site(slug: str, session: AsyncSession = Depends(get_session)):
    site = sites.get_site(slug)
    if not site:
        raise HTTPException(404, "Unknown site")
    provider_id = site.get("tmdb_provider_id")
    if not provider_id:
        return _msg("No TMDB provider id configured for this site.")
    service = (await session.execute(
        select(Service).where(Service.slug == slug)
    )).scalar_one_or_none()
    if not service:
        return _msg("Site not synced to the database yet — restart the app.")

    existing = {(t.tmdb_id, t.media_type.value) for t in (await session.execute(
        select(Title).where(Title.service_id == service.id)
    )).scalars()}

    sem = asyncio.Semaphore(8)

    async def fetch(tmdb_id: int, media_type: str) -> dict:
        async with sem:
            return await tmdb.get_details(tmdb_id, media_type)

    added = skipped = 0
    try:
        for media_type in ("movie", "tv"):
            ids = await tmdb.discover_by_provider(provider_id, media_type,
                                                  limit=PRELOAD_PER_TYPE)
            fresh = [i for i in ids if (i, media_type) not in existing]
            skipped += len(ids) - len(fresh)
            details = await asyncio.gather(*(fetch(i, media_type) for i in fresh))
            for d in details:
                session.add(Title(
                    service_id=service.id,
                    tmdb_id=d["tmdb_id"],
                    media_type=MediaType(d["media_type"]),
                    title=d["title"],
                    overview=d["overview"],
                    poster_url=d["poster_url"],
                    backdrop_url=d["backdrop_url"],
                    runtime_minutes=d["runtime_minutes"],
                    release_year=d["release_year"],
                    genres=d["genres"],
                    deep_link=sites.title_search_link(site, d["title"]),
                ))
                added += 1
    except httpx.HTTPStatusError as exc:
        return _msg(f"TMDB request failed ({exc.response.status_code}) — check TMDB_API_KEY.")
    await session.commit()
    return _msg(f"Added {added} titles" + (f", {skipped} already in library" if skipped else ""),
                tone="emerald")
