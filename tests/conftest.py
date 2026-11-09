from __future__ import annotations

from urllib.parse import urlparse

import pytest

from tests.fakesite import FakeServer, FakeSite


@pytest.fixture(autouse=True)
def _no_proxy_for_loopback(monkeypatch):
    """Never route the loopback test server through a corporate/CI proxy."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture
def site() -> FakeSite:
    return FakeSite()


@pytest.fixture
def memory_fetch(site):
    """fetch(url) -> html straight from memory; raises KeyError for unknown pages."""
    pages = site.build()

    def fetch(url: str) -> str:
        return pages[urlparse(url).path]
    return fetch


@pytest.fixture
def server(site):
    with FakeServer(site) as srv:
        yield srv
