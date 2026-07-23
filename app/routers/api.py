import asyncio
import html
import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import sites
import tmdb
from db import SessionLocal, get_session

log = logging.getLogger(__name__)
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
        mature=details["mature"],
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


@router.patch("/settings/hide-mature")
async def toggle_hide_mature(request: Request,
                             session: AsyncSession = Depends(get_session)):
    profile = await active_profile(request, session)
    profile.hide_mature = not profile.hide_mature
    await session.commit()
    return Response(headers={"HX-Refresh": "true"})


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


# "Add all" pulls a site's TMDB/JustWatch catalog. The button opens an inline
# form asking how many titles to pull (a browser prompt() dialog proved
# unreliable — suppressed dialogs silently cancel the request): 0 or blank
# imports every movie and show the provider lists in-region, no popularity
# floor; a number caps how many movies and how many shows are pulled, most
# popular first. Full imports can be thousands of titles per site and take
# minutes — one detail fetch per new title. That's far too long for a single
# HTTP request (the browser would time out before it ever committed), so the
# import runs as a background task that commits in batches.
PRELOAD_MIN_VOTES = 0    # 0 = no audience floor, include the long tail
PRELOAD_BATCH = 100      # titles fetched + committed per batch (bounds memory /
                         # persists partial progress if the task dies midway)

# Slug -> running import task, so a second click doesn't start a duplicate run.
_preload_tasks: dict[str, asyncio.Task] = {}


async def _run_preload(slug: str, service_id: int, provider_id: int,
                       site: dict, per_type: int | None) -> None:
    """Background worker: walk the provider's catalog (all of it, or the
    per_type most popular of each type), fetching details and committing in
    batches so progress survives a crash or restart."""
    sem = asyncio.Semaphore(8)

    async def fetch(tmdb_id: int, media_type: str) -> dict | None:
        async with sem:
            try:
                return await tmdb.get_details(tmdb_id, media_type)
            except Exception:
                return None  # skip a single bad/rate-limited title, keep going

    added = 0
    try:
        async with SessionLocal() as session:
            existing = {(t.tmdb_id, t.media_type.value) for t in (await session.execute(
                select(Title).where(Title.service_id == service_id)
            )).scalars()}
            for media_type in ("movie", "tv"):
                ids = await tmdb.discover_by_provider(
                    provider_id, media_type,
                    limit=per_type, min_votes=PRELOAD_MIN_VOTES)
                fresh = [i for i in ids if (i, media_type) not in existing]
                for start in range(0, len(fresh), PRELOAD_BATCH):
                    chunk = fresh[start:start + PRELOAD_BATCH]
                    details = await asyncio.gather(
                        *(fetch(i, media_type) for i in chunk))
                    for d in details:
                        if not d:
                            continue
                        session.add(Title(
                            service_id=service_id,
                            tmdb_id=d["tmdb_id"],
                            media_type=MediaType(d["media_type"]),
                            title=d["title"],
                            overview=d["overview"],
                            poster_url=d["poster_url"],
                            backdrop_url=d["backdrop_url"],
                            runtime_minutes=d["runtime_minutes"],
                            release_year=d["release_year"],
                            genres=d["genres"],
                            mature=d["mature"],
                            deep_link=sites.title_search_link(site, d["title"]),
                        ))
                        added += 1
                    await session.commit()
                    log.info("Preload %s: committed %d/%d %s",
                             slug, min(start + PRELOAD_BATCH, len(fresh)),
                             len(fresh), media_type)
        log.info("Preload %s finished: added %d titles", slug, added)
    except asyncio.CancelledError:
        # User hit Stop. Batches already committed above are kept; the
        # in-flight batch (if any) is rolled back when the session closes.
        log.info("Preload %s stopped by user after %d titles", slug, added)
        raise
    except Exception:
        log.exception("Preload %s failed after %d titles", slug, added)


def _preload_running_msg(slug: str) -> Response:
    """Running-import status with a Stop button, swapped into #preload-msg."""
    return Response(
        content=(
            '<span class="text-sm text-emerald-400">Import running in the '
            'background — refresh the page to watch the count climb. </span>'
            f'<button hx-post="/api/sites/{slug}/preload/stop" '
            f'hx-target="#preload-msg-{slug}" hx-swap="innerHTML" '
            'class="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-2 py-1 text-sm">'
            'Stop</button>'),
        media_type="text/html",
    )


@router.post("/sites/{slug}/preload")
async def preload_site(slug: str, count: str = Form("0"),
                       session: AsyncSession = Depends(get_session)):
    site = sites.get_site(slug)
    if not site:
        raise HTTPException(404, "Unknown site")
    provider_id = site.get("tmdb_provider_id")
    if not provider_id:
        return _msg("No TMDB provider id configured for this site.")
    # How many titles of each type to pull. 0/blank = full catalog.
    count = count.strip()
    if count and not count.isdigit():
        return _msg("Enter a number of titles to pull (0 = all).")
    per_type = int(count) if count else 0
    service = (await session.execute(
        select(Service).where(Service.slug == slug)
    )).scalar_one_or_none()
    if not service:
        return _msg("Site not synced to the database yet — restart the app.")

    running = _preload_tasks.get(slug)
    if running and not running.done():
        return _preload_running_msg(slug)

    task = asyncio.create_task(
        _run_preload(slug, service.id, provider_id, site, per_type or None))
    _preload_tasks[slug] = task
    return _preload_running_msg(slug)


@router.post("/sites/{slug}/preload/stop")
async def stop_preload(slug: str):
    task = _preload_tasks.get(slug)
    if not task or task.done():
        return _msg("No import is running for this site.")
    task.cancel()
    return _msg("Import stopped — titles already imported are kept. "
                "Refresh to see the total.", tone="emerald")
