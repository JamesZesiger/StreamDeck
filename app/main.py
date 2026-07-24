import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

import sites
import tmdb
import wikidata
from db import SessionLocal, engine
from models import Account, Base, Service, Title
from routers import accounts, api, pages

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
                # Accounts: profiles belong to an account. NULL account_id
                # rows predate accounts; the first registration adopts them.
                await conn.execute(text(
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
                    "account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE"))
                # Profile names are now unique per account, not globally.
                await conn.execute(text(
                    "ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_name_key"))
                # Sites (and through them titles) are per account: services
                # gain an owner plus the config that used to live in
                # sites.json. Slugs are now unique per account only.
                await conn.execute(text(
                    "ALTER TABLE services ADD COLUMN IF NOT EXISTS "
                    "account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE"))
                await conn.execute(text(
                    "ALTER TABLE services ADD COLUMN IF NOT EXISTS "
                    "tmdb_provider_id INTEGER"))
                await conn.execute(text(
                    "ALTER TABLE services ADD COLUMN IF NOT EXISTS "
                    "search_url VARCHAR(500) NOT NULL DEFAULT ''"))
                await conn.execute(text(
                    "ALTER TABLE services DROP CONSTRAINT IF EXISTS services_slug_key"))
                # The old unique=True produced a unique *index*; replace it
                # with a plain one so slugs can repeat across accounts.
                await conn.execute(text("DROP INDEX IF EXISTS ix_services_slug"))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_services_slug ON services (slug)"))
                # Rows that predate ownership go to the oldest account (no-op
                # when no accounts exist yet — the first registration adopts).
                await conn.execute(text(
                    "UPDATE services SET account_id = (SELECT min(id) FROM accounts) "
                    "WHERE account_id IS NULL"))
                await conn.execute(text(
                    "UPDATE profiles SET account_id = (SELECT min(id) FROM accounts) "
                    "WHERE account_id IS NULL"))
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

    # One-time legacy migration: services created when sites.json was the
    # source of truth are missing provider id / search URL — copy those over
    # by slug. Custom-site icons switch from slug- to id-based URLs (slugs
    # are only unique per account now).
    async with SessionLocal() as session:
        rows = (await session.execute(select(Service))).scalars().all()
        legacy = {s["slug"]: s for s in sites.load_legacy_sites()}
        for row in rows:
            old = legacy.get(row.slug)
            if old:
                if row.tmdb_provider_id is None:
                    row.tmdb_provider_id = old.get("tmdb_provider_id")
                if not row.search_url:
                    row.search_url = old.get("search_url") or ""
            if row.icon_path.startswith("/icons/"):
                row.icon_path = f"/icons/{row.id}.svg"
        # Accounts that registered before sites were per-account own none
        # (adoption gave everything to the oldest account) — seed them the
        # defaults so their Sites and Add pages aren't empty.
        owners = {row.account_id for row in rows}
        accounts = (await session.execute(select(Account))).scalars().all()
        for account in accounts:
            if account.id in owners:
                continue
            for s in sites.DEFAULT_SITES:
                session.add(Service(account_id=account.id, name=s["name"],
                                    slug=s["slug"], base_domain=s["base_domain"],
                                    icon_path=s["icon_path"],
                                    tmdb_provider_id=s["tmdb_provider_id"],
                                    search_url=s["search_url"]))
        await session.commit()


async def _backfill_details() -> None:
    """Best-effort: fetch genres/rating/popularity for titles added before
    those columns existed."""
    try:
        async with SessionLocal() as session:
            provider_by_service = {s.id: s.tmdb_provider_id for s in (
                await session.execute(select(Service))).scalars()}
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
            for (key, titles), details in zip(by_key.items(), results):
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
            services = (await session.execute(select(Service))).scalars().all()
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
            for service in services:
                if not wikidata.supported(service.slug):
                    continue
                # A deep_link starting like the search template is a fallback.
                template = service.search_url or ""
                prefix = template.split("{query}")[0] if "{query}" in template else template
                if not prefix:
                    continue
                rows = (await session.execute(select(Title).where(
                    Title.service_id == service.id,
                    Title.deep_link.like(prefix + "%")))).scalars().all()
                if not rows:
                    continue
                imdb_ids = await asyncio.gather(*(imdb(t) for t in rows))
                links = await wikidata.resolve_links(
                    service.slug,
                    [(i, t.media_type.value) for i, t in zip(imdb_ids, rows)])
                for i, t in zip(imdb_ids, rows):
                    url = links.get(i)
                    if url:
                        t.deep_link = url
                        upgraded += 1
                await session.commit()
                log.info("Deep-link backfill %s: %d/%d upgraded",
                         service.slug, upgraded, len(rows))
        log.info("Deep-link backfill finished: upgraded %d titles", upgraded)
    except Exception:
        log.exception("Deep-link backfill failed")


async def _startup_backfills() -> None:
    await _backfill_details()
    await _backfill_deep_links()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    backfill = asyncio.create_task(_startup_backfills())
    yield
    backfill.cancel()


app = FastAPI(title="StreamDeck", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)
app.include_router(accounts.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
