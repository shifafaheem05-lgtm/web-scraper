"""The scraping pipeline: crawl -> (details) -> filter -> sort -> limit.

Kept free of argument parsing and printing so it can be used as a library and tested directly::

    from webscraper.client import PoliteSession
    from webscraper.pipeline import ScrapeOptions, run

    result = run(ScrapeOptions(max_pages=2, details=True), PoliteSession().get)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .crawl import Fetch, crawl, discover_categories, enrich, resolve_categories
from .exceptions import WebScraperError
from .filters import Filters, sort_with
from .sites import BOOKS, Site

log = logging.getLogger(__name__)

START_URL = "https://books.toscrape.com/catalogue/page-1.html"


@dataclass
class ScrapeOptions:
    url: Optional[str] = None               # first page; default = the site's own start URL
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
    scraped: List[Any]                                            # everything found, before filters
    kept: List[Any]                                               # after filters / sort / limit
    failures: List[Tuple[str, str]] = field(default_factory=list)
    interrupted: bool = False
    incomplete: bool = False        # a page failed mid-crawl; results are what was collected before it


def site_index(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}/index.html"


def _matches(options: ScrapeOptions, site: Site, item: Any) -> bool:
    if site.book_features:
        return options.filters.matches(item)
    needle = options.filters.search
    return not needle or needle.lower() in site.search_text(item).lower()


def _identity(item: Any) -> str:
    """Key used to drop duplicates: the item's URL if it has one, otherwise its full content."""
    return str(getattr(item, "url", None) or repr(item))


def run(options: ScrapeOptions, fetch: Fetch, site: Site = BOOKS) -> ScrapeResult:
    """Run a scrape using ``fetch(url) -> html``. Ctrl+C returns the partial result, not a crash.

    ``site`` says how to read the pages (default: books.toscrape.com).
    """
    if not site.book_features and (options.categories or options.all_categories or options.details):
        raise WebScraperError(f"categories and detail pages are not available for the {site.name!r} site")
    first_url = options.url or site.start_url
    start_urls = [first_url]
    if options.categories or options.all_categories:
        available = discover_categories(fetch, site_index(first_url))
        chosen = available if options.all_categories else resolve_categories(options.categories, available)
        start_urls = [c.url for c in chosen]
        log.info("Scraping %d categor%s", len(chosen), "y" if len(chosen) == 1 else "ies")

    unique: Dict[str, Any] = {}   # de-duplicate, keeping first-seen order
    interrupted = False

    def on_page(n: int, url: str, count: int) -> None:
        log.info("Page %d: %d %s  (%s)", n, count, site.item_noun, url)

    errors: List[WebScraperError] = []
    try:
        for start in start_urls:
            try:
                for item in crawl(fetch, start, options.max_pages, on_page=on_page, parse=site.parse_listing,
                                  next_page=site.find_next, noun=site.item_noun):
                    unique.setdefault(_identity(item), item)
            except WebScraperError as exc:   # e.g. the connection drops on page 17: keep pages 1-16
                log.warning("stopped crawling %s: %s", start, exc)
                errors.append(exc)
    except KeyboardInterrupt:
        interrupted = True
        log.warning("interrupted - keeping the %d %s found so far", len(unique), site.item_noun)

    if errors and not unique:
        raise errors[0]          # nothing at all was scraped: that is an error, not a partial result

    books: List[Any] = list(unique.values())
    failures: List[Tuple[str, str]] = []
    if options.details and books and not interrupted:
        step = max(len(books) // 10, 1)
        log.info("Fetching details for %d books (polite delay applies; Ctrl+C keeps what is done)", len(books))

        def progress(done: int, total: int) -> None:
            if done == total or done % step == 0:
                log.info("Details: %d/%d", done, total)

        enriched = enrich(books, fetch, workers=options.workers, on_progress=progress)
        books, failures, interrupted = enriched.books, enriched.failures, enriched.interrupted

    kept = [b for b in books if _matches(options, site, b)]
    kept = sort_with(kept, site.sort_keys, options.sort, options.descending)
    if options.limit is not None:
        kept = kept[: max(options.limit, 0)]
    return ScrapeResult(books, kept, failures, interrupted, incomplete=bool(errors))
