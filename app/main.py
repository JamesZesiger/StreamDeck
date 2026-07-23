import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

import sites
import tmdb
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
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS "
                    "hide_mature BOOLEAN NOT NULL DEFAULT FALSE"))
                # ADD COLUMN above is a no-op once the column exists (e.g. when
                # create_all just made it without a server default), so set the
                # default unconditionally — the raw seed INSERT below relies on it.
                await conn.execute(text(
                    "ALTER TABLE profiles ALTER COLUMN hide_mature SET DEFAULT FALSE"))
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
    # services table so titles can keep their FK. Credentials stay in the JSON.
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
            rows = (await session.execute(
                select(Title).where((Title.genres == "") | Title.rating.is_(None))
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
                    filled += len(titles)
            await session.commit()
            log.info("Backfilled details for %d of %d titles", filled, len(rows))
    except Exception:
        log.exception("Details backfill failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    backfill = asyncio.create_task(_backfill_details())
    yield
    backfill.cancel()


app = FastAPI(title="StreamDeck", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
