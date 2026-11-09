from unittest import mock

import pytest
import requests

from tests.fakesite import FakeServer, FakeSite
from webscraper.cache import DiskCache
from webscraper.client import PoliteSession
from webscraper.exceptions import FetchError, RobotsDisallowed
from webscraper.ratelimit import RateLimiter


class FakeResponse:
    def __init__(self, text="", status=200, headers=None):
        self.text, self.status_code, self.encoding = text, status, None
        self.headers = headers if headers is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def client(robots, page_status=200, robots_status=None, **kw):
    sess = mock.Mock(spec=requests.Session)
    sess.headers = {}
    sess.proxies = {}

    def get(url, timeout=None):
        if url.endswith("/robots.txt"):
            if isinstance(robots, Exception):
                raise robots
            status = robots_status or (200 if robots is not None else 404)
            return FakeResponse(robots or "", status)
        return FakeResponse("<html>ok</html>", page_status)
    sess.get.side_effect = get
    return PoliteSession(delay=0, session=sess, **kw)


def test_robots_disallow_blocks():
    c = client("User-agent: *\nDisallow: /private/")
    assert not c.allowed("https://x.test/private/a")
    assert c.allowed("https://x.test/public/a")
    with pytest.raises(RobotsDisallowed):
        c.get("https://x.test/private/a")


def test_missing_robots_allows_everything():
    assert client(None).allowed("https://x.test/anything")


def test_robots_5xx_is_treated_as_off_limits():
    assert not client("", robots_status=503).allowed("https://x.test/a")


def test_robots_network_error_is_treated_as_off_limits():
    assert not client(requests.ConnectionError("down")).allowed("https://x.test/a")


def test_ignore_robots_flag():
    c = client("User-agent: *\nDisallow: /", respect_robots=False)
    assert c.get("https://x.test/a") == "<html>ok</html>"


def test_robots_is_fetched_once_per_host():
    c = client("")
    c.get("https://x.test/a"); c.get("https://x.test/b")
    robots_calls = [call for call in c.session.get.call_args_list if call.args[0].endswith("robots.txt")]
    assert len(robots_calls) == 1


def test_crawl_delay_slows_the_limiter():
    c = client("User-agent: *\nCrawl-delay: 7")
    c.allowed("https://x.test/a")
    assert c._limiter.interval == 7


def test_http_error_becomes_fetcherror():
    with pytest.raises(FetchError, match="could not fetch"):
        client("", page_status=404).get("https://x.test/a")


def test_user_agent_and_proxy_are_set():
    c = client("", user_agent="MyBot/1", proxy="http://proxy.test:8080")
    assert c.session.headers["User-Agent"] == "MyBot/1"
    assert c.session.proxies["https"] == "http://proxy.test:8080"


def test_charset_defaulting_fixes_pound_sign():
    resp = requests.Response()
    resp._content = "£5".encode()
    resp.status_code = 200
    resp.headers["content-type"] = "text/html"
    sess = mock.Mock(spec=requests.Session); sess.headers = {}; sess.proxies = {}
    sess.get.return_value = resp
    assert PoliteSession(delay=0, respect_robots=False, session=sess).get("https://x.test/") == "£5"


def test_rate_limiter_spaces_requests():
    now, sleeps = [100.0], []
    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=sleeps.append)
    assert limiter.wait() == 0        # first request goes straight out
    assert limiter.wait() == 2.0      # second must wait the full interval
    now[0] += 5                       # plenty of time passes
    assert limiter.wait() == 0
    limiter.raise_interval(1)         # can never speed up
    assert limiter.interval == 2.0
    limiter.raise_interval(9)
    assert limiter.interval == 9.0


def test_disk_cache_roundtrip_ttl_and_clear(tmp_path):
    cache = DiskCache(tmp_path / "c", ttl=3600)
    assert cache.get("u") is None
    cache.set("u", "héllo £")
    assert cache.get("u") == "héllo £"
    assert DiskCache(tmp_path / "c", ttl=0).get("u") is None     # ttl 0 = always stale
    assert DiskCache(tmp_path / "c", ttl=None).get("u") == "héllo £"
    assert cache.clear() == 1 and cache.get("u") is None


# ---- against a real HTTP server on loopback --------------------------------------------
def test_real_http_get_caching_and_retry(tmp_path):
    site = FakeSite(count=3)
    with FakeServer(site, flaky_once={"/catalogue/page-1.html"}) as srv:
        c = PoliteSession(delay=0, retries=2, cache=DiskCache(tmp_path))
        html = c.get(srv.start_url)           # first attempt gets a 503, retry succeeds
        assert "Light Story 1" in html and "£" in html   # no 'Â£' mojibake
        assert c.requests_made == 1
        before = len(srv.hits)
        assert c.get(srv.start_url) == html   # served from the cache
        assert len(srv.hits) == before and c.cache_hits == 1


def test_real_http_robots_disallow(tmp_path):
    site = FakeSite(count=3, robots="User-agent: *\nDisallow: /catalogue/")
    with FakeServer(site) as srv, pytest.raises(RobotsDisallowed):
        PoliteSession(delay=0).get(srv.start_url)
