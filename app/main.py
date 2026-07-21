import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

import sites
from db import SessionLocal, engine
from models import Base, PlaybackMode, Service
from routers import api, pages

log = logging.getLogger(__name__)


async def _init_db(retries: int = 10) -> None:
    for attempt in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
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
                row.playback_mode = PlaybackMode(site["playback_mode"])
            else:
                session.add(Service(
                    name=site["name"],
                    slug=site["slug"],
                    base_domain=site["base_domain"],
                    icon_path=site["icon_path"],
                    playback_mode=PlaybackMode(site["playback_mode"]),
                ))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    yield


app = FastAPI(title="StreamDeck", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
