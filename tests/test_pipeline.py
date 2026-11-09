from tests.fakesite import FakeSite
from webscraper import Filters, ScrapeOptions, run

START = "https://books.toscrape.com/catalogue/page-1.html"


def test_run_defaults(memory_fetch):
    result = run(ScrapeOptions(max_pages=None), memory_fetch)
    assert len(result.scraped) == len(result.kept) == 45
    assert not result.failures and not result.interrupted


def test_filter_sort_limit(memory_fetch):
    opts = ScrapeOptions(max_pages=None, filters=Filters(min_rating=4, in_stock_only=True), sort="price",
                         descending=True, limit=5)
    kept = run(opts, memory_fetch).kept
    assert len(kept) == 5
    assert [b.price for b in kept] == sorted((b.price for b in kept), reverse=True)
    assert all(b.rating >= 4 and b.in_stock for b in kept)


def test_limit_zero(memory_fetch):
    assert run(ScrapeOptions(limit=0), memory_fetch).kept == []


def test_single_category(memory_fetch):
    result = run(ScrapeOptions(categories=("poetry",), max_pages=None, details=True), memory_fetch)
    assert len(result.kept) == 15 and {b.category for b in result.kept} == {"Poetry"}


def test_all_categories_deduplicates_and_covers_everything(memory_fetch):
    result = run(ScrapeOptions(all_categories=True, max_pages=None), memory_fetch)
    assert len(result.scraped) == 45


def test_details_and_search_on_description(memory_fetch):
    opts = ScrapeOptions(max_pages=1, details=True, filters=Filters(search="tale about harbor"))
    kept = run(opts, memory_fetch).kept
    assert kept and all("harbor" in (b.description or "").lower() for b in kept)


def test_details_failures_reported_but_run_completes():
    from urllib.parse import urlparse
    pages = FakeSite(count=5, broken_details={1, 4}).build()
    result = run(ScrapeOptions(details=True), lambda u: pages[urlparse(u).path])
    assert len(result.failures) == 2 and len(result.kept) == 5


def test_keyboard_interrupt_during_crawl_returns_partial_results(site):
    from urllib.parse import urlparse
    pages = site.build()
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return pages[urlparse(url).path]
    result = run(ScrapeOptions(max_pages=None, details=True), fetch)
    assert result.interrupted and len(result.scraped) == 20 and len(result.kept) == 20
