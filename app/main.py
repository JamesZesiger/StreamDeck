import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from db import SessionLocal, engine
from models import Base, PlaybackMode, Service
from routers import api, pages
from services_registry import SEED_SERVICES

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

    async with SessionLocal() as session:
        existing = set((await session.execute(select(Service.slug))).scalars())
        for seed in SEED_SERVICES:
            if seed["slug"] not in existing:
                session.add(Service(
                    name=seed["name"],
                    slug=seed["slug"],
                    base_domain=seed["base_domain"],
                    icon_path=seed["icon_path"],
                    playback_mode=PlaybackMode(seed["playback_mode"]),
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
