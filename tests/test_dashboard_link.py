"""The nav's Dashboard button: dashBoard's port on the browser's host."""

from types import SimpleNamespace

import pytest

from routers import pages


def _request(scheme, hostname):
    return SimpleNamespace(url=SimpleNamespace(scheme=scheme, hostname=hostname))


@pytest.fixture(autouse=True)
def dashboard_on(monkeypatch):
    """homenet sets DASHBOARD_PORT; these tests run as if it were 8080."""
    monkeypatch.setattr(pages.settings, "dashboard_port", 8080)


def test_hidden_without_a_dashboard(monkeypatch):
    monkeypatch.setattr(pages.settings, "dashboard_port", None)
    assert pages.dashboard_url(_request("http", "localhost")) is None


def test_uses_the_host_the_browser_used():
    assert pages.dashboard_url(_request("http", "homenet-pc")) == "http://homenet-pc:8080"


def test_brackets_ipv6_hosts():
    assert pages.dashboard_url(_request("http", "::1")) == "http://[::1]:8080"


def test_falls_back_to_localhost():
    assert pages.dashboard_url(_request("http", None)) == "http://localhost:8080"


def test_port_follows_settings(monkeypatch):
    monkeypatch.setattr(pages.settings, "dashboard_port", 9090)
    assert pages.dashboard_url(_request("http", "localhost")) == "http://localhost:9090"
