"""Site registry: URL safety, domain cleaning, slug detection, CRUD."""

import pytest

import sites


class TestIsHttpUrl:
    @pytest.mark.parametrize("url", [
        "https://www.netflix.com/title/1",
        "http://example.com/x",
        "https://play.max.com/search?q={query}",
    ])
    def test_accepts_http_and_https(self, url):
        assert sites.is_http_url(url)

    @pytest.mark.parametrize("url", [
        "javascript:alert(1)",
        "data:text/html,hi",
        "vbscript:msgbox(1)",
        "netflix.com/title/1",
        "https://",
        "",
    ])
    def test_rejects_everything_else(self, url):
        assert not sites.is_http_url(url)


class TestDomainAndSlug:
    def test_slugify_strips_non_alphanumerics(self):
        assert sites.slugify("Prime Video!") == "primevideo"

    def test_clean_domain_normalizes(self):
        assert sites._clean_domain("https://www.Netflix.com/browse") == "netflix.com"

    def test_clean_domain_requires_a_dot(self):
        with pytest.raises(ValueError):
            sites._clean_domain("localhost")


class TestSearchLink:
    def test_query_template_is_filled_and_encoded(self):
        site = {"search_url": "https://x.com/s?q={query}"}
        assert sites.title_search_link(site, "The Bear & Co") == \
            "https://x.com/s?q=The+Bear+%26+Co"

    def test_no_template_falls_back_to_site(self):
        site = {"search_url": "", "base_domain": "x.com"}
        assert sites.title_search_link(site, "anything") == "https://www.x.com"


class TestDetectServiceSlug:
    def test_exact_and_subdomain_match(self):
        assert sites.detect_service_slug("https://www.netflix.com/title/1") == "netflix"
        assert sites.detect_service_slug("https://play.max.com/show/2") == "max"

    def test_alt_domains(self):
        assert sites.detect_service_slug("https://www.amazon.com/gp/video/x") == "primevideo"

    def test_unknown_and_unparseable(self):
        assert sites.detect_service_slug("https://example.org/x") is None
        assert sites.detect_service_slug("javascript:alert(1)") is None


class TestRegistry:
    def test_first_load_seeds_defaults(self):
        loaded = sites.load_sites()
        assert {s["slug"] for s in loaded} >= {"netflix", "hulu", "youtube"}

    def test_stored_credentials_are_scrubbed(self):
        seeded = sites.load_sites()
        seeded[0]["username"] = "someone"
        seeded[0]["password"] = "hunter2"
        sites.save_sites(seeded)
        reloaded = sites.load_sites()
        assert all("password" not in s and "username" not in s for s in reloaded)
        assert all("password" not in s for s in sites.load_sites())  # rewritten on disk

    def test_add_site(self):
        site = sites.add_site("Criterion Channel", "criterionchannel.com")
        assert site["slug"] == "criterionchannel"
        assert sites.get_site("criterionchannel")["base_domain"] == "criterionchannel.com"

    def test_add_duplicate_raises(self):
        sites.add_site("Criterion", "criterion.com")
        with pytest.raises(ValueError):
            sites.add_site("Criterion", "other.com")

    def test_update_site_rejects_unsafe_search_url(self):
        sites.load_sites()
        with pytest.raises(ValueError):
            sites.update_site("netflix", "Netflix", "netflix.com", 8,
                              "javascript:alert(1)")

    def test_update_site_saves_fields(self):
        sites.load_sites()
        updated = sites.update_site("netflix", "Netflix US", "netflix.com", 8,
                                    "https://www.netflix.com/search?q={query}",
                                    search_links_only=True)
        assert updated["name"] == "Netflix US"
        assert updated["search_links_only"] is True

    def test_update_unknown_slug_raises(self):
        sites.load_sites()
        with pytest.raises(ValueError):
            sites.update_site("nope", "Nope", "nope.com", None, "")


class TestSearchButtons:
    def test_off_by_default(self):
        assert not any(s.get("search_button") for s in sites.load_sites())
        assert not sites.search_buttons("the bear")

    def test_update_site_saves_search_button(self):
        sites.load_sites()
        updated = sites.update_site("netflix", "Netflix", "netflix.com", 8,
                                    "https://www.netflix.com/search?q={query}",
                                    search_button=True)
        assert updated["search_button"] is True
        assert sites.get_site("netflix")["search_button"] is True

    def test_links_sites_with_button_on(self):
        sites.load_sites()
        sites.update_site("netflix", "Netflix", "netflix.com", 8,
                          "https://www.netflix.com/search?q={query}",
                          search_button=True)
        assert sites.search_buttons("the bear") == [{
            "name": "Netflix",
            "icon_path": "/static/icons/netflix.svg",
            "url": "https://www.netflix.com/search?q=the+bear",
        }]

    def test_needs_a_query(self):
        sites.load_sites()
        sites.update_site("netflix", "Netflix", "netflix.com", 8,
                          "https://www.netflix.com/search?q={query}",
                          search_button=True)
        assert not sites.search_buttons("   ")

    def test_skips_search_url_without_query_placeholder(self):
        sites.load_sites()
        sites.update_site("netflix", "Netflix", "netflix.com", 8,
                          "https://www.netflix.com", search_button=True)
        assert not sites.search_buttons("the bear")

    def test_respects_allowed_services(self):
        sites.load_sites()
        sites.update_site("netflix", "Netflix", "netflix.com", 8,
                          "https://www.netflix.com/search?q={query}",
                          search_button=True)
        assert not sites.search_buttons("the bear", allowed={"hulu"})
        assert sites.search_buttons("the bear", allowed={"netflix"})
