"""Active-profile resolution. The chosen profile id lives in a cookie; the
library is shared between profiles, watch state and watch lists are not."""

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Profile

COOKIE = "profile_id"
COOKIE_MAX_AGE = 365 * 24 * 3600


async def active_profile(request: Request, session: AsyncSession) -> Profile:
    """The profile from the cookie, falling back to the first profile.
    _init_db guarantees at least one profile exists."""
    pid = request.cookies.get(COOKIE, "")
    if pid.isdigit():
        profile = await session.get(Profile, int(pid))
        if profile:
            return profile
    return (await session.execute(
        select(Profile).order_by(Profile.id))).scalars().first()


def set_profile_cookie(response: Response, profile_id: int) -> None:
    response.set_cookie(COOKIE, str(profile_id),
                        max_age=COOKIE_MAX_AGE, samesite="lax")
