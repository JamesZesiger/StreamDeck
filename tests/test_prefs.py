"""PIN hashing, secret key, and stored-preference behavior."""

import hashlib

import prefs


class TestPinHashing:
    def test_hash_is_salted_pbkdf2(self):
        stored = prefs.hash_pin("1234")
        assert stored.startswith(f"pbkdf2_sha256${prefs.PIN_ITERATIONS}$")

    def test_same_pin_hashes_differently(self):
        assert prefs.hash_pin("1234") != prefs.hash_pin("1234")

    def test_verify_accepts_correct_pin(self):
        assert prefs.verify_pin("1234", prefs.hash_pin("1234"))

    def test_verify_strips_whitespace(self):
        assert prefs.verify_pin(" 1234 ", prefs.hash_pin("1234"))

    def test_verify_rejects_wrong_pin(self):
        assert not prefs.verify_pin("9999", prefs.hash_pin("1234"))

    def test_verify_rejects_empty_stored(self):
        assert not prefs.verify_pin("1234", "")

    def test_verify_survives_malformed_stored(self):
        assert not prefs.verify_pin("1234", "pbkdf2_sha256$zz$nothex$nothex")
        assert not prefs.verify_pin("1234", "$$$")

    def test_legacy_sha256_hash_still_verifies(self):
        legacy = hashlib.sha256(b"1234").hexdigest()
        assert prefs.is_legacy_pin_hash(legacy)
        assert prefs.verify_pin("1234", legacy)
        assert not prefs.verify_pin("9999", legacy)

    def test_new_format_is_not_legacy(self):
        assert not prefs.is_legacy_pin_hash(prefs.hash_pin("1234"))
        assert not prefs.is_legacy_pin_hash("")

    def test_set_pin_roundtrip(self):
        prefs.set_pin("4321")
        assert prefs.verify_pin("4321", prefs.get_pin_hash())


class TestSecretKey:
    def test_generated_once_and_persisted(self):
        key = prefs.get_secret_key()
        assert len(key) == 64
        assert prefs.get_secret_key() == key


class TestStoredPrefs:
    def test_language_defaults_without_file(self):
        assert prefs.get_language() == prefs.DEFAULT_LANGUAGE

    def test_language_roundtrip(self):
        prefs.set_language("de-DE")
        prefs._language = None  # drop the cache; force a re-read from disk
        assert prefs.get_language() == "de-DE"

    def test_region_roundtrip(self):
        prefs.set_region("CA")
        prefs._region = None
        assert prefs.get_region() == "CA"

    def test_theme_merges_with_defaults(self):
        prefs.set_theme({"accent": "blue"})
        theme = prefs.get_theme()
        assert theme["accent"] == "blue"
        assert theme["bg_mode"] == prefs.DEFAULT_THEME["bg_mode"]

    def test_theme_unknown_accent_falls_back(self):
        prefs.set_theme({"accent": "hotdog"})
        assert prefs.get_theme()["accent"] == prefs.DEFAULT_THEME["accent"]
