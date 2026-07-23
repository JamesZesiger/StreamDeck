import asyncio
import html
import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import prefs
import sites
import tmdb
from db import SessionLocal, get_session

log = logging.getLogger(__name__)
from models import (MediaType, Profile, ProfileListItem, ProfileWatch, Service,
                    Title)
from profiles import (PIN_COOKIE, PIN_UNLOCK_SECONDS, RATING_CAPS,
                      active_profile, set_profile_cookie, settings_locked)

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
        rating=details["rating"],
        vote_count=details["vote_count"],
        popularity=details["popularity"],
        certification=details["certification"],
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


# Kid mode: while the active profile has it on (and a PIN exists), settings
# changes and profile switching require the PIN. Entering it sets a
# short-lived cookie; endpoints check that server-side, the menus render a
# PIN form instead of their contents until then.
async def _unlocked_profile(request: Request, session: AsyncSession) -> Profile:
    profile = await active_profile(request, session)
    if settings_locked(profile, request):
        raise HTTPException(403, "PIN required")
    return profile


@router.post("/pin/unlock")
async def pin_unlock(pin: str = Form(...)):
    stored = prefs.get_pin_hash()
    if not stored or prefs.hash_pin(pin) != stored:
        return _msg("Wrong PIN.")
    response = Response(headers={"HX-Refresh": "true"})
    response.set_cookie(PIN_COOKIE, stored, max_age=PIN_UNLOCK_SECONDS,
                        httponly=True, samesite="lax")
    return response


@router.post("/pin/lock")
async def pin_lock():
    """Re-engage the kid-mode lock right away instead of waiting out the
    5-minute unlock window (e.g. before handing the device back)."""
    response = Response(headers={"HX-Refresh": "true"})
    response.delete_cookie(PIN_COOKIE)
    return response


@router.patch("/settings/rating-cap")
async def set_rating_cap(request: Request, level: str = Form(""),
                         session: AsyncSession = Depends(get_session)):
    profile = await _unlocked_profile(request, session)
    valid = {str(lvl) for lvl, _ in RATING_CAPS}
    profile.max_rating_level = int(level) if level in valid else None
    await session.commit()
    return Response(headers={"HX-Refresh": "true"})


@router.patch("/settings/service-toggle")
async def toggle_allowed_service(request: Request, slug: str = Form(...),
                                 session: AsyncSession = Depends(get_session)):
    profile = await _unlocked_profile(request, session)
    all_slugs = set((await session.execute(
        select(Service.slug).where(Service.enabled))).scalars())
    if slug not in all_slugs:
        raise HTTPException(404, "Unknown service")
    # "" means every service is allowed; expand it before toggling one off.
    allowed = {s.strip() for s in (profile.allowed_services or "").split(",")
               if s.strip()} or set(all_slugs)
    allowed.symmetric_difference_update({slug})
    # Collapse back to "" when everything is allowed again.
    profile.allowed_services = ("" if allowed >= all_slugs
                                else ",".join(sorted(allowed)))
    await session.commit()
    return Response(headers={"HX-Refresh": "true"})


@router.patch("/settings/kid-mode")
async def toggle_kid_mode(request: Request, pin: str = Form(""),
                          session: AsyncSession = Depends(get_session)):
    profile = await _unlocked_profile(request, session)
    if not profile.kid_mode and not prefs.get_pin_hash():
        # First enable anywhere: a PIN must exist or the lock means nothing.
        pin = pin.strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            return _msg("Set a 4–8 digit PIN to turn on kid mode.")
        prefs.set_pin(pin)
    profile.kid_mode = not profile.kid_mode
    await session.commit()
    return Response(headers={"HX-Refresh": "true"})


@router.post("/settings/pin")
async def change_pin(request: Request, pin: str = Form(...),
                     session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
    pin = pin.strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        return _msg("PIN must be 4–8 digits.")
    prefs.set_pin(pin)
    return _msg("PIN saved.", tone="emerald")


@router.post("/profiles")
async def create_profile(request: Request, name: str = Form(...),
                         session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
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
async def activate_profile(request: Request, profile_id: int,
                           session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
    if not await session.get(Profile, profile_id):
        raise HTTPException(404, "Unknown profile")
    response = Response(headers={"HX-Refresh": "true"})
    set_profile_cookie(response, profile_id)
    return response


@router.delete("/profiles/{profile_id}")
async def delete_profile(request: Request, profile_id: int,
                         session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
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
async def delete_title(request: Request, title_id: int,
                       session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)  # removes from the shared library
    title = await session.get(Title, title_id)
    if title:
        # Remove the combined title: every provider's row.
        await session.execute(delete(Title).where(
            Title.tmdb_id == title.tmdb_id, Title.media_type == title.media_type))
        await session.commit()
    return Response(headers={"HX-Redirect": "/"})


def _msg(text: str, tone: str = "amber") -> Response:
    return Response(
        content=f'<p class="text-sm text-{tone}-400">{html.escape(text)}</p>',
        media_type="text/html",
    )


@router.post("/sites")
async def create_site(
    request: Request,
    name: str = Form(...),
    base_domain: str = Form(...),
    tmdb_provider_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    await _unlocked_profile(request, session)
    provider_id = int(tmdb_provider_id) if tmdb_provider_id.strip().isdigit() else None
    try:
        site = sites.add_site(name, base_domain, tmdb_provider_id=provider_id)
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
    request: Request,
    slug: str,
    name: str = Form(...),
    base_domain: str = Form(...),
    tmdb_provider_id: str = Form(""),
    search_url: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    await _unlocked_profile(request, session)
    provider_id = int(tmdb_provider_id) if tmdb_provider_id.strip().isdigit() else None
    try:
        site = sites.update_site(slug, name, base_domain,
                                 provider_id, search_url)
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
async def remove_all_titles(request: Request, slug: str,
                            session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
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
                            rating=d["rating"],
                            vote_count=d["vote_count"],
                            popularity=d["popularity"],
                            certification=d["certification"],
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
async def preload_site(request: Request, slug: str, count: str = Form("0"),
                       session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
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


# Changing the metadata language re-fetches every title's TMDB details in the
# background so stored text (title, overview, genres) switches language too.
_language_refresh_task: asyncio.Task | None = None


async def _refresh_metadata() -> None:
    sem = asyncio.Semaphore(8)

    async def fetch(tmdb_id: int, media_type: str) -> dict | None:
        async with sem:
            try:
                return await tmdb.get_details(tmdb_id, media_type)
            except Exception:
                return None

    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(Title))).scalars().all()
            by_key: dict[tuple, list[Title]] = {}
            for t in rows:
                by_key.setdefault((t.tmdb_id, t.media_type.value), []).append(t)
            keys = list(by_key)
            for start in range(0, len(keys), 100):
                chunk = keys[start:start + 100]
                details = await asyncio.gather(*(fetch(tid, mt) for tid, mt in chunk))
                for key, d in zip(chunk, details):
                    if not d:
                        continue
                    for t in by_key[key]:
                        t.title = d["title"]
                        t.overview = d["overview"]
                        t.genres = d["genres"]
                        t.poster_url = d["poster_url"]
                        t.backdrop_url = d["backdrop_url"]
                        t.rating = d["rating"]
                        t.vote_count = d["vote_count"]
                        t.popularity = d["popularity"]
                        t.certification = d["certification"]
                await session.commit()
                log.info("Language refresh: %d/%d titles",
                         min(start + 100, len(keys)), len(keys))
        log.info("Language refresh finished: %d titles", len(keys))
    except asyncio.CancelledError:
        log.info("Language refresh superseded by a newer language change")
        raise
    except Exception:
        log.exception("Language refresh failed")


@router.post("/settings/language")
async def change_language(request: Request, lang: str = Form(...),
                          session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
    if lang not in {code for code, _, _ in prefs.LANGUAGES}:
        raise HTTPException(400, "Unknown language")
    if lang != prefs.get_language():
        prefs.set_language(lang)
        from routers import pages
        pages._collection_cache.clear()  # cached in the old language
        global _language_refresh_task
        # A newer language wins: abandon any refresh still running and
        # restart so every title ends up in the language picked last.
        if _language_refresh_task and not _language_refresh_task.done():
            _language_refresh_task.cancel()
        _language_refresh_task = asyncio.create_task(_refresh_metadata())
    return Response(headers={"HX-Refresh": "true"})


@router.post("/sites/{slug}/preload/stop")
async def stop_preload(request: Request, slug: str,
                       session: AsyncSession = Depends(get_session)):
    await _unlocked_profile(request, session)
    task = _preload_tasks.get(slug)
    if not task or task.done():
        return _msg("No import is running for this site.")
    task.cancel()
    return _msg("Import stopped — titles already imported are kept. "
                "Refresh to see the total.", tone="emerald")
