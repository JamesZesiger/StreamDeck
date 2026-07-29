"""Shared test setup.

App modules are flat scripts under app/ that read SITES_FILE when config.py
is imported, so the temp data dir goes into the environment before anything
from app/ lands on sys.path.
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
    """Fresh prefs/sites files and caches for every test."""
    import prefs

    for f in DATA_DIR.glob("*"):
        f.unlink()
    prefs._language = None
    prefs._region = None
    prefs._theme = None
    yield
