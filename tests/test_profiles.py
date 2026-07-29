"""Unlock tokens, rating caps, and per-profile policy checks."""

import time

import prefs
import profiles
from models import Profile, Title


class FakeRequest:
    def __init__(self, pin_cookie=None):
        self.cookies = {} if pin_cookie is None else {profiles.PIN_COOKIE: pin_cookie}


class TestPinToken:
    def test_valid_token_unlocks(self):
        prefs.set_pin("1234")
        assert profiles.pin_unlocked(FakeRequest(profiles.make_pin_token()))

    def test_no_stored_pin_never_unlocks(self):
        assert not profiles.pin_unlocked(FakeRequest(profiles.make_pin_token()))

    def test_tampered_token_rejected(self):
        prefs.set_pin("1234")
        token = profiles.make_pin_token()
        flipped = token[:-1] + ("0" if token[-1] != "0" else "1")
        assert not profiles.pin_unlocked(FakeRequest(flipped))

    def test_garbage_and_missing_tokens_rejected(self):
        prefs.set_pin("1234")
        assert not profiles.pin_unlocked(FakeRequest("garbage"))
        assert not profiles.pin_unlocked(FakeRequest(""))
        assert not profiles.pin_unlocked(FakeRequest())

    def test_expired_token_rejected(self):
        prefs.set_pin("1234")
        expires = str(int(time.time()) - 1)
        token = f"{expires}.{profiles._pin_signature(expires)}"
        assert not profiles.pin_unlocked(FakeRequest(token))

    def test_raw_hash_cookie_rejected(self):
        # The pre-token scheme stored the PIN hash itself in the cookie.
        prefs.set_pin("1234")
        assert not profiles.pin_unlocked(FakeRequest(prefs.get_pin_hash()))

    def test_pin_change_invalidates_outstanding_tokens(self):
        prefs.set_pin("1234")
        token = profiles.make_pin_token()
        prefs.set_pin("5678")
        assert not profiles.pin_unlocked(FakeRequest(token))


class TestSettingsLocked:
    def test_kid_mode_with_pin_locks(self):
        prefs.set_pin("1234")
        profile = Profile(name="kid", kid_mode=True)
        assert profiles.settings_locked(profile, FakeRequest())

    def test_unlock_token_opens_kid_mode(self):
        prefs.set_pin("1234")
        profile = Profile(name="kid", kid_mode=True)
        request = FakeRequest(profiles.make_pin_token())
        assert not profiles.settings_locked(profile, request)

    def test_no_kid_mode_never_locks(self):
        prefs.set_pin("1234")
        profile = Profile(name="adult", kid_mode=False)
        assert not profiles.settings_locked(profile, FakeRequest())

    def test_no_stored_pin_fails_open(self):
        profile = Profile(name="kid", kid_mode=True)
        assert not profiles.settings_locked(profile, FakeRequest())


class TestCertLevels:
    def test_known_certifications(self):
        assert profiles.cert_level("G") == 0
        assert profiles.cert_level("tv-14") == 2
        assert profiles.cert_level(" R ") == 3

    def test_unknown_certification_is_none(self):
        assert profiles.cert_level("NR") is None
        assert profiles.cert_level("") is None
        assert profiles.cert_level(None) is None


class TestTitleAllowed:
    def test_no_cap_allows_everything(self):
        profile = Profile(name="p", max_rating_level=None)
        assert profiles.title_allowed(profile, Title(certification=None, mature=True))

    def test_cap_hides_unrated(self):
        profile = Profile(name="p", max_rating_level=3)
        assert not profiles.title_allowed(profile, Title(certification="", mature=False))

    def test_cap_compares_levels(self):
        profile = Profile(name="p", max_rating_level=1)
        assert profiles.title_allowed(profile, Title(certification="PG", mature=False))
        assert not profiles.title_allowed(profile, Title(certification="PG-13", mature=False))

    def test_mature_flag_needs_top_cap(self):
        title = Title(certification="PG", mature=True)
        assert not profiles.title_allowed(Profile(name="p", max_rating_level=2), title)
        assert profiles.title_allowed(Profile(name="p", max_rating_level=3), title)


class TestAllowedServiceSlugs:
    def test_empty_means_unrestricted(self):
        assert profiles.allowed_service_slugs(Profile(name="p", allowed_services="")) is None
        assert profiles.allowed_service_slugs(Profile(name="p", allowed_services=None)) is None

    def test_parses_csv(self):
        profile = Profile(name="p", allowed_services="netflix, hulu,")
        assert profiles.allowed_service_slugs(profile) == {"netflix", "hulu"}
