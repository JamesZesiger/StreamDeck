"""Active-profile resolution and per-profile content policy. The chosen
profile id lives in a cookie; the library is shared between profiles, watch
state and watch lists are not."""

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import prefs
from models import Profile, Title

COOKIE = "profile_id"
COOKIE_MAX_AGE = 365 * 24 * 3600

# Unified age levels across US movie and TV certifications, for the
# per-profile rating cap. Anything not listed counts as unrated.
CERT_LEVELS = {
    "G": 0, "TV-Y": 0, "TV-G": 0,
    "PG": 1, "TV-Y7": 1, "TV-Y7-FV": 1, "TV-PG": 1,
    "PG-13": 2, "TV-14": 2,
    "R": 3, "NC-17": 3, "TV-MA": 3,
}
# (level, label) choices for the settings menu; None = no cap.
RATING_CAPS = [
    (0, "All ages (G, TV-Y, TV-G)"),
    (1, "Ages 7+ (PG, TV-Y7, TV-PG)"),
    (2, "Teens (PG-13, TV-14)"),
    (3, "Mature (R, TV-MA)"),
]

# Short-lived proof that the parent PIN was entered; value is the PIN hash.
PIN_COOKIE = "pin_ok"
PIN_UNLOCK_SECONDS = 300


def cert_level(certification: str | None) -> int | None:
    return CERT_LEVELS.get((certification or "").strip().upper())


def allowed_service_slugs(profile: Profile) -> set[str] | None:
    """Slugs this profile may see, or None when unrestricted."""
    slugs = {s.strip() for s in (profile.allowed_services or "").split(",") if s.strip()}
    return slugs or None


def title_allowed(profile: Profile, title: Title) -> bool:
    """Rating-cap check (service checks happen in queries). With a cap set,
    unrated titles are hidden — safe default for kid profiles — and TMDB's
    adult flag needs the top cap regardless of certification."""
    if profile.max_rating_level is None:
        return True
    if title.mature and profile.max_rating_level < 3:
        return False
    level = cert_level(title.certification)
    return level is not None and level <= profile.max_rating_level


def pin_unlocked(request: Request) -> bool:
    stored = prefs.get_pin_hash()
    return bool(stored) and request.cookies.get(PIN_COOKIE) == stored


def settings_locked(profile: Profile, request: Request) -> bool:
    """Kid mode locks settings and profile switching behind the PIN. If no
    PIN is stored (e.g. prefs.json was hand-edited), nothing can verify one,
    so fail open — fixing that requires filesystem access anyway."""
    return profile.kid_mode and bool(prefs.get_pin_hash()) and not pin_unlocked(request)


async def active_profile(request: Request, session: AsyncSession) -> Profile:
    """The signed-in account's profile from the cookie, falling back to the
    account's first profile. This is also the sign-in gate: without a valid
    session it raises a redirect to /login, so every endpoint that resolves
    a profile requires an account."""
    account = await auth.require_account(request, session)
    pid = request.cookies.get(COOKIE, "")
    if pid.isdigit():
        profile = await session.get(Profile, int(pid))
        if profile and profile.account_id == account.id:
            return profile
    profile = (await session.execute(
        select(Profile).where(Profile.account_id == account.id)
        .order_by(Profile.id))).scalars().first()
    if not profile:
        # Registration seeds one profile per account; recover if it's gone.
        profile = Profile(name=account.username, account_id=account.id)
        session.add(profile)
        await session.commit()
    return profile


def set_profile_cookie(response: Response, profile_id: int) -> None:
    response.set_cookie(COOKIE, str(profile_id),
                        max_age=COOKIE_MAX_AGE, samesite="lax")
