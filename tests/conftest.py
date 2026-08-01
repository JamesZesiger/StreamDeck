"""Shared test setup.

App modules are flat scripts under app/ that read SITES_FILE when config.py
is imported, so the temp data dir goes into the environment before anything
from app/ lands on sys.path.

Preferences live in the database (app_prefs). Tests point prefs at a
throwaway sqlite file instead of Postgres — prefs owns a synchronous
engine, so stdlib sqlite3 is enough and no server is needed.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"

DATA_DIR = Path(tempfile.mkdtemp(prefix="streamdeck-tests-"))
os.environ["SITES_FILE"] = str(DATA_DIR / "sites.json")

sys.path.insert(0, str(APP_DIR))


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh prefs database, sites file, and caches for every test."""
    from sqlalchemy import create_engine

    import prefs
    from models import AppPref, Base

    if prefs._engine is not None:
        prefs._engine.dispose()
    for f in DATA_DIR.glob("*"):
        f.unlink()
    prefs._cache = None
    prefs._engine = create_engine(f"sqlite:///{DATA_DIR / 'prefs.db'}")
    Base.metadata.create_all(prefs._engine, tables=[AppPref.__table__])
    yield
