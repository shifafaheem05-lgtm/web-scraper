import threading
import time

import pytest

from tests.fakesite import FakeSite
from webscraper import ScrapeError, crawl, enrich
from webscraper.crawl import discover_categories, resolve_categories
from webscraper.exceptions import FetchError

BASE = "https://books.toscrape.com/catalogue/page-1.html"


def test_crawl_all_pages(memory_fetch):
    books = list(crawl(memory_fetch, BASE))
    assert len(books) == 45
    assert books[0].title == "Light Story 1" and books[-1].title == "Attic Story 45"


def test_crawl_order_and_count_per_page(memory_fetch):
    seen = []
    list(crawl(memory_fetch, BASE, on_page=lambda n, u, c: seen.append((n, c))))
    assert seen == [(1, 20), (2, 20), (3, 5)]


def test_max_pages(memory_fetch):
    assert len(list(crawl(memory_fetch, BASE, max_pages=2))) == 40


def test_loop_protection(site):
    page = site.build()["/catalogue/page-1.html"].replace("page-2.html", "page-1.html")
    assert len(list(crawl(lambda u: page, BASE))) == 20


def test_wrong_site_raises_with_url():
    with pytest.raises(ScrapeError, match="no books found"):
        list(crawl(lambda u: "<html><body>nothing here</body></html>", BASE))


def test_categories_discovery_and_resolution(memory_fetch):
    cats = discover_categories(memory_fetch, "https://books.toscrape.com/index.html")
    assert [c.name for c in resolve_categories(["mystery", " TRAVEL "], cats)] == ["Mystery", "Travel"]
    assert len(resolve_categories(["travel", "Travel"], cats)) == 1  # de-duplicated


def test_unknown_category_suggests_close_match(memory_fetch):
    cats = discover_categories(memory_fetch, "https://books.toscrape.com/index.html")
    with pytest.raises(ScrapeError, match="Did you mean: Mystery"):
        resolve_categories(["Mistery"], cats)


def test_no_categories_raises():
    with pytest.raises(ScrapeError):
        discover_categories(lambda u: "<html></html>", "https://x.test/index.html")


def test_enrich_fills_details_in_order(memory_fetch):
    books = list(crawl(memory_fetch, BASE, max_pages=1))
    result = enrich(books, memory_fetch, workers=4)
    assert not result.failures
    assert [b.title for b in result.books] == [b.title for b in books]
    assert all(b.upc and b.category for b in result.books)


def test_enrich_survives_a_broken_detail_page():
    site = FakeSite(count=6, broken_details={2})
    pages = site.build()
    from urllib.parse import urlparse
    fetch = lambda u: pages[urlparse(u).path]  # noqa: E731
    books = list(crawl(fetch, BASE))
    result = enrich(books, fetch, workers=3)
    assert len(result.failures) == 1 and "velvet-story-2_2" in result.failures[0][0]
    assert result.books[1].upc is None          # kept listing data only
    assert result.books[0].upc == "upc0001"     # the others still enriched
    assert len(result.books) == 6


def test_enrich_captures_fetch_errors(memory_fetch):
    books = list(crawl(memory_fetch, BASE, max_pages=1))[:3]

    def flaky(url):
        if "velvet-story-2_2" in url:
            raise FetchError("boom")
        return memory_fetch(url)
    result = enrich(books, flaky, workers=2)
    assert [f[1] for f in result.failures] == ["boom"]


def test_enrich_really_runs_in_parallel(memory_fetch):
    books = list(crawl(memory_fetch, BASE, max_pages=1))[:8]
    active, peak, lock = 0, 0, threading.Lock()

    def slow(url):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return memory_fetch(url)
    enrich(books, slow, workers=4)
    assert peak > 1


def test_enrich_progress_callback(memory_fetch):
    books = list(crawl(memory_fetch, BASE, max_pages=1))[:5]
    seen = []
    enrich(books, memory_fetch, workers=2, on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (5, 5) and len(seen) == 5
