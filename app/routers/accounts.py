"""Account registration/sign-in and the admin area's separate credentials."""

import html

from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import prefs
import sites
from db import get_session
from models import Account, Profile, Service

router = APIRouter(prefix="/api")


def _msg(text: str, tone: str = "amber") -> Response:
    return Response(
        content=f'<p class="text-sm text-{tone}-400">{html.escape(text)}</p>',
        media_type="text/html",
    )


@router.post("/auth/register")
async def register(username: str = Form(...), password: str = Form(...),
                   session: AsyncSession = Depends(get_session)):
    username = username.strip()
    error = auth.credential_error(username, password)
    if error:
        return _msg(error)
    exists = (await session.execute(select(Account).where(
        func.lower(Account.username) == username.lower()))).scalar_one_or_none()
    if exists:
        return _msg("That username is taken.")
    account = Account(username=username,
                      password_hash=auth.hash_password(password))
    session.add(account)
    await session.flush()
    total = (await session.execute(
        select(func.count()).select_from(Account))).scalar_one()
    if total == 1:
        # The first account adopts profiles and sites created before accounts
        # existed (existing installs keep their library and watch history).
        await session.execute(update(Profile).where(
            Profile.account_id.is_(None)).values(account_id=account.id))
        await session.execute(update(Service).where(
            Service.account_id.is_(None)).values(account_id=account.id))
    owned = (await session.execute(select(func.count()).select_from(Profile)
             .where(Profile.account_id == account.id))).scalar_one()
    if not owned:
        session.add(Profile(name=username[:50], account_id=account.id))
    owned_sites = (await session.execute(select(func.count()).select_from(Service)
                   .where(Service.account_id == account.id))).scalar_one()
    if not owned_sites:
        for s in sites.DEFAULT_SITES:
            session.add(Service(account_id=account.id, name=s["name"],
                                slug=s["slug"], base_domain=s["base_domain"],
                                icon_path=s["icon_path"],
                                tmdb_provider_id=s["tmdb_provider_id"],
                                search_url=s["search_url"]))
    await session.commit()
    response = Response(headers={"HX-Redirect": "/"})
    auth.set_session_cookie(response, account.id)
    return response


@router.post("/auth/login")
async def login(username: str = Form(...), password: str = Form(...),
                session: AsyncSession = Depends(get_session)):
    account = (await session.execute(select(Account).where(
        func.lower(Account.username) == username.strip().lower()
    ))).scalar_one_or_none()
    if not account or not auth.verify_password(password, account.password_hash):
        return _msg("Wrong username or password.")
    response = Response(headers={"HX-Redirect": "/"})
    auth.set_session_cookie(response, account.id)
    return response


@router.post("/auth/logout")
async def logout():
    response = Response(headers={"HX-Redirect": "/login"})
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@router.post("/admin/setup")
async def admin_setup(username: str = Form(...), password: str = Form(...)):
    """First-visit claim of the admin credentials; refused once they exist
    (changing them afterwards means editing prefs.json)."""
    if prefs.get_admin_hash():
        return _msg("Admin credentials are already set.")
    username = username.strip()
    error = auth.credential_error(username, password)
    if error:
        return _msg(error)
    prefs.set_admin(username, auth.hash_password(password))
    response = Response(headers={"HX-Redirect": "/admin"})
    auth.set_admin_cookie(response)
    return response


@router.post("/admin/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    stored = prefs.get_admin_hash()
    if (not stored or username.strip() != prefs.get_admin_user()
            or not auth.verify_password(password, stored)):
        return _msg("Wrong admin username or password.")
    response = Response(headers={"HX-Redirect": "/admin"})
    auth.set_admin_cookie(response)
    return response


@router.post("/admin/logout")
async def admin_logout():
    response = Response(headers={"HX-Redirect": "/admin"})
    response.delete_cookie(auth.ADMIN_COOKIE)
    return response
