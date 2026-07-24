"""Account and admin-area authentication.

Accounts are username+password rows in Postgres (no email); the browser
holds an HMAC-signed, expiring session cookie, so there's no server-side
session table. The admin area (/admin, currently an empty placeholder) uses
its own single credential pair stored in prefs.json — deliberately separate
from user accounts — with a much shorter-lived cookie.
"""

import hashlib
import hmac
import re
import secrets
import time

from fastapi import HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

import prefs
from models import Account

SESSION_COOKIE = "session"
SESSION_SECONDS = 30 * 24 * 3600
ADMIN_COOKIE = "admin_session"
ADMIN_SESSION_SECONDS = 3600

PBKDF2_ROUNDS = 200_000
USERNAME_RE = re.compile(r"[A-Za-z0-9_.-]{3,32}")


def credential_error(username: str, password: str) -> str | None:
    """Validation message for a new username+password pair, or None if ok."""
    if not USERNAME_RE.fullmatch(username):
        return "Username must be 3–32 letters, digits, . _ or -."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                             bytes.fromhex(salt), PBKDF2_ROUNDS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt), PBKDF2_ROUNDS)
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), expected)


def _sign(payload: str) -> str:
    return hmac.new(prefs.get_session_secret().encode(),
                    payload.encode(), hashlib.sha256).hexdigest()


def make_token(kind: str, ident: str, max_age: int) -> str:
    payload = f"{kind}:{ident}:{int(time.time()) + max_age}"
    return f"{payload}:{_sign(payload)}"


def parse_token(value: str, kind: str) -> str | None:
    """The token's ident if the signature checks out and it hasn't expired."""
    try:
        t_kind, ident, exp, sig = value.split(":")
    except (AttributeError, ValueError):
        return None
    if not hmac.compare_digest(_sign(f"{t_kind}:{ident}:{exp}"), sig):
        return None
    if t_kind != kind or int(exp) < time.time():
        return None
    return ident


def _redirect(request: Request, target: str, detail: str) -> HTTPException:
    """401 + HX-Redirect for htmx partial requests (htmx follows the header
    even on error responses), plain 303 for full-page navigation."""
    if request.headers.get("hx-request") == "true":
        return HTTPException(401, detail, headers={"HX-Redirect": target})
    return HTTPException(303, detail, headers={"Location": target})


async def current_account(request: Request, session: AsyncSession) -> Account | None:
    ident = parse_token(request.cookies.get(SESSION_COOKIE, ""), "account")
    if ident and ident.isdigit():
        return await session.get(Account, int(ident))
    return None


async def require_account(request: Request, session: AsyncSession) -> Account:
    account = await current_account(request, session)
    if not account:
        raise _redirect(request, "/login", "Sign in required")
    return account


def set_session_cookie(response: Response, account_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE, make_token("account", str(account_id), SESSION_SECONDS),
        max_age=SESSION_SECONDS, httponly=True, samesite="lax")


def admin_authed(request: Request) -> bool:
    return parse_token(request.cookies.get(ADMIN_COOKIE, ""), "admin") == "ok"


def require_admin(request: Request) -> None:
    """Guard for future admin-only endpoints."""
    if not admin_authed(request):
        raise _redirect(request, "/admin", "Admin sign-in required")


def set_admin_cookie(response: Response) -> None:
    response.set_cookie(
        ADMIN_COOKIE, make_token("admin", "ok", ADMIN_SESSION_SECONDS),
        max_age=ADMIN_SESSION_SECONDS, httponly=True, samesite="lax")
