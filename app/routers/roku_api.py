"""JSON API for the sideloaded Roku channel (../rokuStreamDeck).

Everything else in the app speaks htmx HTML fragments; a BrightScript client
needs JSON, so the Roku surface lives here. Read-only browse + a launch relay
— no profiles, watch state, or PIN (MVP scope). LAN-trusted like the rest of
the app: no auth.
"""

import ipaddress
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import roku
from db import get_session
from models import MediaType, Service, Title

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roku")


def _resize(url: str | None, size: str) -> str | None:
    """TMDB image URLs embed the size as a path segment; stored rows use
    w500. The Roku grid wants smaller (w342), backdrops bigger (w780)."""
    if not url:
        return None
    return url.replace("/t/p/w500/", f"/t/p/{size}/")


@router.get("/services")
async def services(session: AsyncSession = Depends(get_session)):
    counts = dict((await session.execute(
        select(Title.service_id, func.count(Title.id))
        .group_by(Title.service_id))).all())
    rows = (await session.execute(
        select(Service).where(Service.enabled).order_by(Service.name)
    )).scalars().all()
    return {"services": [{
        "id": s.id,
        "slug": s.slug,
        "name": s.name,
        "roku_channel_id": roku.channel_id(s.slug),
        "title_count": counts.get(s.id, 0),
    } for s in rows]}


@router.get("/library")
async def library(
    service: str | None = None,
    type: str | None = None,
    sort: str = "rating",
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = select(Title).options(selectinload(Title.service))
    if service:
        query = query.join(Service).where(Service.slug == service)
    if type in ("movie", "tv"):
        query = query.where(Title.media_type == MediaType(type))
    titles = (await session.execute(query)).scalars().all()

    # Grouping + weighted rating mirror pages.library() (see the comments
    # there); kept lean here — no profile/watched/region logic per MVP scope.
    by_key: dict[tuple, list[Title]] = {}
    for t in titles:
        by_key.setdefault((t.tmdb_id, t.media_type), []).append(t)
    groups = []
    for rows in by_key.values():
        rows = sorted(rows, key=lambda r: r.service.name.lower())
        stats = max(rows, key=lambda r: r.vote_count or 0)
        groups.append({
            "primary": rows[0],
            "services": [r.service.slug for r in rows],
            "added": max(r.added_at for r in rows),
            "raw_rating": stats.rating or 0,
            "votes": stats.vote_count or 0,
        })
    prior_votes = 500  # Bayesian prior, same constant as pages.library()
    rated = [g for g in groups if g["raw_rating"] and g["votes"]]
    mean = sum(g["raw_rating"] for g in rated) / len(rated) if rated else 0
    for g in groups:
        v, r = g["votes"], g["raw_rating"]
        g["rating"] = ((v * r + prior_votes * mean) / (v + prior_votes)
                       if v and r else 0)

    if sort == "added":
        groups.sort(key=lambda g: g["primary"].title.lower())
        groups.sort(key=lambda g: g["added"], reverse=True)
    elif sort == "title":
        groups.sort(key=lambda g: g["primary"].title.lower())
    elif sort == "year":
        groups.sort(key=lambda g: g["rating"], reverse=True)
        groups.sort(key=lambda g: g["primary"].release_year or 0, reverse=True)
    else:  # "rating"
        groups.sort(key=lambda g: g["votes"], reverse=True)
        groups.sort(key=lambda g: g["rating"], reverse=True)

    if limit is not None:
        groups = groups[offset:offset + limit]
    return {"count": len(groups), "titles": [{
        "id": g["primary"].id,
        "tmdb_id": g["primary"].tmdb_id,
        "media_type": g["primary"].media_type.value,
        "title": g["primary"].title,
        "year": g["primary"].release_year,
        "rating": round(g["rating"], 1) if g["rating"] else None,
        "certification": g["primary"].certification or None,
        "runtime_minutes": g["primary"].runtime_minutes,
        "poster": _resize(g["primary"].poster_url, "w342"),
        "services": g["services"],
    } for g in groups]}


@router.get("/titles/{title_id}")
async def title_detail(title_id: int,
                       session: AsyncSession = Depends(get_session)):
    title = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.id == title_id))).scalar_one_or_none()
    if not title:
        raise HTTPException(404, "Title not found")
    siblings = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.tmdb_id == title.tmdb_id,
               Title.media_type == title.media_type)
    )).scalars().all()
    providers = sorted(siblings, key=lambda r: r.service.name.lower())
    return {
        "id": title.id,
        "tmdb_id": title.tmdb_id,
        "media_type": title.media_type.value,
        "title": title.title,
        "overview": title.overview,
        "year": title.release_year,
        "runtime_minutes": title.runtime_minutes,
        "genres": [g.strip() for g in title.genres.split(",") if g.strip()],
        "certification": title.certification or None,
        "rating": title.rating,
        "vote_count": title.vote_count,
        "poster": _resize(title.poster_url, "w342"),
        "backdrop": _resize(title.backdrop_url, "w780"),
        "providers": [{
            "title_id": p.id,
            "service": p.service.slug,
            "service_name": p.service.name,
            "unavailable": p.unavailable_since is not None,
            "roku": roku.launch_params(
                p.service.slug, p.media_type.value, p.deep_link),
        } for p in providers],
    }


class LaunchRequest(BaseModel):
    title_id: int
    device_ip: str


@router.post("/launch")
async def launch(body: LaunchRequest,
                 session: AsyncSession = Depends(get_session)):
    """ECP relay: launch the title's channel on the Roku that asked. The
    Roku sends its own LAN IP; ECP from another LAN device is the supported
    path (what the Roku mobile app does), so the server fires the request."""
    try:
        if not ipaddress.ip_address(body.device_ip).is_private:
            raise ValueError
    except ValueError:
        raise HTTPException(400, "device_ip must be a private LAN address")
    title = (await session.execute(
        select(Title).options(selectinload(Title.service))
        .where(Title.id == body.title_id))).scalar_one_or_none()
    if not title:
        raise HTTPException(404, "Title not found")
    params = roku.launch_params(
        title.service.slug, title.media_type.value, title.deep_link)
    if not params:
        raise HTTPException(
            422, {"ok": False, "reason": "no_roku_app",
                  "service": title.service.slug})
    url = f"http://{body.device_ip}:8060{params['ecp_path']}"
    log.info("Roku launch: %s -> %s", title.title, url)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(url)
        # 200/204 normally, 303 when the channel is already running.
        if r.status_code >= 400:
            log.warning("Roku launch got HTTP %d from %s", r.status_code, url)
            return {"ok": False, "reason": f"ecp_http_{r.status_code}",
                    "ecp_path": params["ecp_path"]}
    except httpx.HTTPError as e:
        # Can't reach the device (different subnet, Docker network, ECP
        # disabled) — tell the app so it can try self-ECP.
        log.warning("Roku launch unreachable %s: %s", url, e)
        return {"ok": False, "reason": "device_unreachable",
                "ecp_path": params["ecp_path"]}
    return {"ok": True, **params}
