import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

import prefs
import sites
import tmdb
import wikidata
from db import SessionLocal, engine
from models import Base, Service, Title
from routers import api, pages

log = logging.getLogger(__name__)


async def _init_db(retries: int = 10) -> None:
    for attempt in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # No Alembic: create_all won't drop removed columns, so retire
                # the old neko-era playback_mode column (and its enum type) here.
                await conn.execute(text(
                    "ALTER TABLE services DROP COLUMN IF EXISTS playback_mode"))
                await conn.execute(text("DROP TYPE IF EXISTS playback_mode"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "genres VARCHAR(300) NOT NULL DEFAULT ''"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "mature BOOLEAN NOT NULL DEFAULT FALSE"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "rating DOUBLE PRECISION"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "vote_count INTEGER"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "popularity DOUBLE PRECISION"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "certification VARCHAR(20)"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "regions TEXT"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "imdb_id VARCHAR(20)"))
                await conn.execute(text(
                    "ALTER TABLE titles ADD COLUMN IF NOT EXISTS "
                    "unavailable_since TIMESTAMPTZ"))
                # hide_mature is retired: the age rating cap replaces it.
                await conn.execute(text(
                    "ALTER TABLE profiles DROP COLUMN IF EXISTS hide_mature"))
                await conn.execute(text(
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
                    "max_rating_level INTEGER"))
                await conn.execute(text(
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
                    "allowed_services VARCHAR(500) NOT NULL DEFAULT ''"))
                await conn.execute(text(
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
                    "kid_mode BOOLEAN NOT NULL DEFAULT FALSE"))
                # Profiles: the library is shared, watch state is per profile.
                # Seed one profile, move the legacy global watched flag into
                # it, then retire the old columns.
                await conn.execute(text(
                    "INSERT INTO profiles (name) SELECT 'Default' "
                    "WHERE NOT EXISTS (SELECT 1 FROM profiles)"))
                legacy_watched = (await conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='titles' AND column_name='watched'"))).first()
                if legacy_watched:
                    await conn.execute(text(
                        "INSERT INTO profile_watches (profile_id, tmdb_id, media_type, watched_at) "
                        "SELECT (SELECT id FROM profiles ORDER BY id LIMIT 1), "
                        "       t.tmdb_id, t.media_type, now() "
                        "FROM (SELECT DISTINCT tmdb_id, media_type FROM titles WHERE watched) t "
                        "ON CONFLICT DO NOTHING"))
                    await conn.execute(text("ALTER TABLE titles DROP COLUMN watched"))
                await conn.execute(text(
                    "ALTER TABLE titles DROP COLUMN IF EXISTS last_played_at"))
            break
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2)

    # sites.json is the source of truth for the site list; sync it into the
    # services table so titles can keep their FK.
    async with SessionLocal() as session:
        rows = {s.slug: s for s in (await session.execute(select(Service))).scalars()}
        for site in sites.load_sites():
            row = rows.get(site["slug"])
            if row:
                row.name = site["name"]
                row.base_domain = site["base_domain"]
                row.icon_path = site["icon_path"]
            else:
                session.add(Service(
                    name=site["name"],
                    slug=site["slug"],
                    base_domain=site["base_domain"],
                    icon_path=site["icon_path"],
                ))
        await session.commit()


async def _backfill_details() -> None:
    """Best-effort: fetch genres/rating/popularity for titles added before
    those columns existed."""
    try:
        async with SessionLocal() as session:
            slugs = {s.id: s.slug for s in (
                await session.execute(select(Service))).scalars()}
            site_providers = {s["slug"]: s.get("tmdb_provider_id")
                              for s in sites.load_sites()}
            provider_by_service = {sid: site_providers.get(slug)
                                   for sid, slug in slugs.items()}
            rows = (await session.execute(
                select(Title).where((Title.genres == "")
                                    | Title.rating.is_(None)
                                    | Title.certification.is_(None)
                                    | Title.regions.is_(None)
                                    | Title.imdb_id.is_(None))
            )).scalars().all()
            if not rows:
                return
            by_key: dict[tuple, list[Title]] = {}
            for t in rows:
                by_key.setdefault((t.tmdb_id, t.media_type.value), []).append(t)

            sem = asyncio.Semaphore(4)

            async def fetch(tmdb_id: int, media_type: str) -> dict | None:
                async with sem:
                    try:
                        return await tmdb.get_details(tmdb_id, media_type)
                    except Exception:
                        return None

            results = await asyncio.gather(
                *(fetch(tid, mt) for tid, mt in by_key))
            filled = 0
            for (_key, titles), details in zip(by_key.items(), results):
                if details:
                    for t in titles:
                        t.genres = details["genres"]
                        t.mature = details["mature"]
                        t.rating = details["rating"]
                        t.vote_count = details["vote_count"]
                        t.popularity = details["popularity"]
                        t.certification = details["certification"]
                        t.imdb_id = details["imdb_id"]
                        t.regions = tmdb.regions_for_provider(
                            details["provider_regions"],
                            provider_by_service.get(t.service_id))
                    filled += len(titles)
            await session.commit()
            log.info("Backfilled details for %d of %d titles", filled, len(rows))
    except Exception:
        log.exception("Details backfill failed")


async def _backfill_deep_links() -> None:
    """Best-effort: upgrade search-page fallback links to direct title pages
    via Wikidata, for services with a known streaming-id property. Titles
    Wikidata doesn't know keep their search link."""
    try:
        async with SessionLocal() as session:
            services = {s.id: s.slug for s in (
                await session.execute(select(Service))).scalars()}
            site_by_slug = {s["slug"]: s for s in sites.load_sites()}
            sem = asyncio.Semaphore(4)

            async def imdb(t: Title) -> str:
                # Stored on the row since the details backfill; only titles it
                # missed (NULL) still need the external_ids call.
                if t.imdb_id is not None:
                    return t.imdb_id
                async with sem:
                    try:
                        return await tmdb.get_imdb_id(t.tmdb_id, t.media_type.value)
                    except Exception:
                        return ""

            upgraded = 0
            for service_id, slug in services.items():
                site = site_by_slug.get(slug)
                if (not site or site.get("search_links_only")
                        or not wikidata.supported(slug)):
                    continue
                # A deep_link starting like the search template is a fallback.
                template = site.get("search_url") or ""
                prefix = template.split("{query}")[0] if "{query}" in template else template
                if not prefix:
                    continue
                rows = (await session.execute(select(Title).where(
                    Title.service_id == service_id,
                    Title.deep_link.like(prefix + "%")))).scalars().all()
                if not rows:
                    continue
                imdb_ids = await asyncio.gather(*(imdb(t) for t in rows))
                links = await wikidata.resolve_links(
                    slug, [(i, t.media_type.value) for i, t in zip(imdb_ids, rows)])
                for i, t in zip(imdb_ids, rows):
                    url = links.get(i)
                    if url:
                        t.deep_link = url
                        upgraded += 1
                await session.commit()
                log.info("Deep-link backfill %s: %d/%d upgraded",
                         slug, upgraded, len(rows))
        log.info("Deep-link backfill finished: upgraded %d titles", upgraded)
    except Exception:
        log.exception("Deep-link backfill failed")


AVAILABILITY_REFRESH_SECONDS = 7 * 24 * 3600


async def _refresh_availability() -> None:
    """Re-check watch-provider data for the whole library: update each row's
    regions and flag titles their service no longer streams anywhere (clear
    the flag if a title comes back). Custom sites without a TMDB provider id
    can't be checked and are left alone."""
    try:
        async with SessionLocal() as session:
            site_by_slug = {s["slug"]: s for s in sites.load_sites()}
            provider_by_service = {
                svc.id: site_by_slug.get(svc.slug, {}).get("tmdb_provider_id")
                for svc in (await session.execute(select(Service))).scalars()}
            rows = [t for t in (await session.execute(select(Title))).scalars()
                    if provider_by_service.get(t.service_id)]
            by_key: dict[tuple, list[Title]] = {}
            for t in rows:
                by_key.setdefault((t.tmdb_id, t.media_type.value), []).append(t)

            sem = asyncio.Semaphore(4)

            async def fetch(tmdb_id: int, media_type: str) -> dict | None:
                async with sem:
                    try:
                        return await tmdb.get_providers(tmdb_id, media_type)
                    except Exception:
                        return None  # TMDB blip: leave this title untouched

            results = await asyncio.gather(
                *(fetch(tid, mt) for tid, mt in by_key))
            now = datetime.now(timezone.utc)
            flagged = cleared = 0
            for (_key, titles), provider_regions in zip(by_key.items(), results):
                if provider_regions is None:
                    continue
                for t in titles:
                    t.regions = tmdb.regions_for_provider(
                        provider_regions, provider_by_service[t.service_id])
                    if t.regions:
                        if t.unavailable_since is not None:
                            cleared += 1
                        t.unavailable_since = None
                    elif t.unavailable_since is None:
                        t.unavailable_since = now
                        flagged += 1
            await session.commit()
            log.info("Availability refresh: %d titles checked, %d newly "
                     "unavailable, %d back", len(rows), flagged, cleared)
    except Exception:
        log.exception("Availability refresh failed")


async def _startup_backfills() -> None:
    await _backfill_details()
    await _backfill_deep_links()
    while True:
        await _refresh_availability()
        await asyncio.sleep(AVAILABILITY_REFRESH_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_db()
    prefs.warm_cache()
    backfill = asyncio.create_task(_startup_backfills())
    yield
    backfill.cancel()


app = FastAPI(title="StreamDeck", lifespan=lifespan)


@app.middleware("http")
async def same_origin_guard(request: Request, call_next):
    """CSRF defense: every state change here is a cookie-authenticated
    browser request, so its Origin (or Referer) must match the host the
    browser is talking to. Requests with neither header come from
    non-browser clients, which cross-site pages can't forge."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin is None:
            referer = request.headers.get("referer")
            origin_host = urlparse(referer).netloc if referer else None
        else:
            # "Origin: null" (sandboxed iframes etc.) parses to "" — rejected.
            origin_host = urlparse(origin).netloc
        if origin_host is not None and origin_host != request.url.netloc:
            return PlainTextResponse("Cross-origin request rejected",
                                     status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
