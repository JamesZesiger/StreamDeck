"""HTTP-level tests: same-origin CSRF guard, PIN unlock flow, and input
validation. These run without a database — every request here is either
rejected by the middleware/validation or served from prefs alone."""

# pylint: disable=redefined-outer-name  # pytest fixtures shadow their own name

import hashlib
import os

import pytest

import prefs
from conftest import APP_DIR

SAME_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(scope="module")
def client():
    os.chdir(APP_DIR)  # static/ and templates/ are cwd-relative
    from fastapi.testclient import TestClient
    from main import app

    # No context manager: skipping lifespan skips the Postgres init.
    return TestClient(app, base_url="http://testserver")


class TestSameOriginGuard:
    def test_cross_origin_post_rejected(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers={"Origin": "http://evil.example"})
        assert r.status_code == 403

    def test_null_origin_rejected(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers={"Origin": "null"})
        assert r.status_code == 403

    def test_same_origin_post_passes(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers=SAME_ORIGIN)
        assert r.status_code == 200

    def test_referer_fallback_same_origin_passes(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers={"Referer": "http://testserver/settings"})
        assert r.status_code == 200

    def test_referer_fallback_cross_origin_rejected(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers={"Referer": "http://evil.example/attack"})
        assert r.status_code == 403

    def test_headerless_client_allowed(self, client):
        # curl-style requests send neither header; cross-site pages can't.
        r = client.post("/api/pin/unlock", data={"pin": "1234"})
        assert r.status_code == 200

    def test_get_requests_unaffected(self, client):
        assert client.get("/healthz").status_code == 200


class TestPinUnlock:
    def test_wrong_pin_rejected(self, client):
        prefs.set_pin("1234")
        r = client.post("/api/pin/unlock", data={"pin": "9999"},
                        headers=SAME_ORIGIN)
        assert r.status_code == 200 and "Wrong PIN" in r.text

    def test_no_stored_pin_rejected(self, client):
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers=SAME_ORIGIN)
        assert "Wrong PIN" in r.text

    def test_correct_pin_sets_signed_token(self, client):
        prefs.set_pin("1234")
        r = client.post("/api/pin/unlock", data={"pin": "1234"},
                        headers=SAME_ORIGIN)
        token = r.cookies.get("pin_ok", "")
        expires, _, signature = token.partition(".")
        assert r.status_code == 200
        assert expires.isdigit() and len(signature) == 64
        assert token != prefs.get_pin_hash()

    def test_legacy_hash_unlocks_and_upgrades(self, client):
        prefs._save("pin_hash", hashlib.sha256(b"4321").hexdigest())
        r = client.post("/api/pin/unlock", data={"pin": "4321"},
                        headers=SAME_ORIGIN)
        assert r.status_code == 200 and "pin_ok" in r.cookies
        assert prefs.get_pin_hash().startswith("pbkdf2_sha256$")

    def test_lock_clears_cookie(self, client):
        r = client.post("/api/pin/lock", headers=SAME_ORIGIN)
        assert r.status_code == 200
        assert 'pin_ok="";' in r.headers.get("set-cookie", "")


class TestCreateTitleValidation:
    def test_rejects_javascript_url(self, client):
        r = client.post("/api/titles",
                        data={"url": "javascript:alert(1)", "service_id": 1,
                              "tmdb_id": 1, "media_type": "movie"},
                        headers=SAME_ORIGIN)
        assert r.status_code == 400

    def test_rejects_unknown_media_type(self, client):
        r = client.post("/api/titles",
                        data={"url": "https://netflix.com/title/1",
                              "service_id": 1, "tmdb_id": 1,
                              "media_type": "banana"},
                        headers=SAME_ORIGIN)
        assert r.status_code == 400
