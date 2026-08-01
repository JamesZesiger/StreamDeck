"""PIN hashing, secret key, and stored-preference behavior."""

import hashlib
import json

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
    def test_language_defaults_when_unset(self):
        assert prefs.get_language() == prefs.DEFAULT_LANGUAGE

    def test_language_roundtrip(self):
        prefs.set_language("de-DE")
        prefs._cache = None  # drop the cache; force a re-read from the table
        assert prefs.get_language() == "de-DE"

    def test_region_roundtrip(self):
        prefs.set_region("CA")
        prefs._cache = None
        assert prefs.get_region() == "CA"

    def test_wrong_stored_type_falls_back_to_default(self):
        prefs._save("region", {"not": "a string"})
        prefs._cache = None
        assert prefs.get_region() == prefs.DEFAULT_REGION

    def test_theme_merges_with_defaults(self):
        prefs.set_theme({"accent": "blue"})
        theme = prefs.get_theme()
        assert theme["accent"] == "blue"
        assert theme["bg_mode"] == prefs.DEFAULT_THEME["bg_mode"]

    def test_theme_unknown_accent_falls_back(self):
        prefs.set_theme({"accent": "hotdog"})
        assert prefs.get_theme()["accent"] == prefs.DEFAULT_THEME["accent"]


class TestLegacyFileImport:
    """Installs that predate the app_prefs table keep their prefs.json
    values: the first read of an empty table imports the file."""

    def _write_legacy(self, data):
        path = prefs._legacy_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_values_are_imported(self):
        self._write_legacy({"language": "ja-JP", "region": "JP",
                            "theme": {"accent": "violet"}})
        assert prefs.get_language() == "ja-JP"
        assert prefs.get_region() == "JP"
        assert prefs.get_theme()["accent"] == "violet"

    def test_imported_pin_still_verifies(self):
        self._write_legacy({"pin_hash": prefs.hash_pin("1234")})
        assert prefs.verify_pin("1234", prefs.get_pin_hash())

    def test_import_persists_to_the_table(self):
        self._write_legacy({"language": "ko-KR"})
        prefs.get_language()          # triggers the import
        prefs._legacy_file().unlink()  # file gone: the table must answer now
        prefs._cache = None
        assert prefs.get_language() == "ko-KR"

    def test_stored_values_win_over_the_file(self):
        prefs.set_language("fr-FR")
        self._write_legacy({"language": "de-DE"})
        prefs._cache = None
        assert prefs.get_language() == "fr-FR"

    def test_malformed_file_is_ignored(self):
        prefs._legacy_file().parent.mkdir(parents=True, exist_ok=True)
        prefs._legacy_file().write_text("{not json", encoding="utf-8")
        assert prefs.get_language() == prefs.DEFAULT_LANGUAGE
