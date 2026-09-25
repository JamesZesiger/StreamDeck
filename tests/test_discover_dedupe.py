"""'Add all' walks TMDB's popularity-sorted pages, which can repeat a title
when popularity shifts mid-walk; each id must come back only once."""

import asyncio

import tmdb


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Serves canned discover pages, keyed by page number."""

    def __init__(self, pages):
        self.pages = pages

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, _url, params):
        page = params["page"]
        return _FakeResponse({"results": [{"id": i} for i in self.pages[page]],
                              "total_pages": len(self.pages)})


def _discover(monkeypatch, pages, limit):
    monkeypatch.setattr(tmdb.httpx, "AsyncClient", lambda **_: _FakeClient(pages))
    return asyncio.run(tmdb.discover_by_provider(8, "tv", limit=limit, region="US"))


def test_repeated_ids_across_pages_come_back_once(monkeypatch):
    pages = {1: [1, 2, 3], 2: [3, 4, 2], 3: [5]}
    assert _discover(monkeypatch, pages, limit=None) == [1, 2, 3, 4, 5]


def test_limit_counts_unique_titles(monkeypatch):
    pages = {1: [1, 2], 2: [2, 3], 3: [4]}
    assert _discover(monkeypatch, pages, limit=3) == [1, 2, 3]
