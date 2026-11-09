"""The scraping pipeline: crawl -> (details) -> filter -> sort -> limit.

Kept free of argument parsing and printing so it can be used as a library and tested directly::

    from webscraper.client import PoliteSession
    from webscraper.pipeline import ScrapeOptions, run

    result = run(ScrapeOptions(max_pages=2, details=True), PoliteSession().get)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .crawl import Fetch, crawl, discover_categories, enrich, resolve_categories
from .filters import Filters, sort_books
from .models import Book

log = logging.getLogger(__name__)

START_URL = "https://books.toscrape.com/catalogue/page-1.html"


@dataclass
class ScrapeOptions:
    url: str = START_URL
    max_pages: Optional[int] = 3            # per start URL; None = every page
    categories: Tuple[str, ...] = ()        # scrape these categories instead of the whole catalogue
    all_categories: bool = False
    details: bool = False                   # also visit each book's page
    workers: int = 4
    filters: Filters = field(default_factory=Filters)
    sort: Optional[str] = None
    descending: bool = False
    limit: Optional[int] = None


@dataclass
class ScrapeResult:
    scraped: List[Book]                                           # everything found, before filters
    kept: List[Book]                                              # after filters / sort / limit
    failures: List[Tuple[str, str]] = field(default_factory=list)
    interrupted: bool = False


def site_index(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}/index.html"


def run(options: ScrapeOptions, fetch: Fetch) -> ScrapeResult:
    """Run a scrape using ``fetch(url) -> html``. Ctrl+C returns the partial result, not a crash."""
    start_urls = [options.url]
    if options.categories or options.all_categories:
        available = discover_categories(fetch, site_index(options.url))
        chosen = available if options.all_categories else resolve_categories(options.categories, available)
        start_urls = [c.url for c in chosen]
        log.info("Scraping %d categor%s", len(chosen), "y" if len(chosen) == 1 else "ies")

    unique: Dict[str, Book] = {}   # de-duplicate by URL, keeping first-seen order
    interrupted = False

    def on_page(n: int, url: str, count: int) -> None:
        log.info("Page %d: %d books  (%s)", n, count, url)

    try:
        for start in start_urls:
            for book in crawl(fetch, start, options.max_pages, on_page=on_page):
                unique.setdefault(book.url, book)
    except KeyboardInterrupt:
        interrupted = True
        log.warning("interrupted - keeping the %d books found so far", len(unique))

    books = list(unique.values())
    failures: List[Tuple[str, str]] = []
    if options.details and books and not interrupted:
        step = max(len(books) // 10, 1)

        def progress(done: int, total: int) -> None:
            if done == total or done % step == 0:
                log.info("Details: %d/%d", done, total)

        enriched = enrich(books, fetch, workers=options.workers, on_progress=progress)
        books, failures, interrupted = enriched.books, enriched.failures, enriched.interrupted

    kept = [b for b in books if options.filters.matches(b)]
    kept = sort_books(kept, options.sort, options.descending)
    if options.limit is not None:
        kept = kept[: max(options.limit, 0)]
    return ScrapeResult(books, kept, failures, interrupted)
