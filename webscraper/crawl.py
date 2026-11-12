"""Crawling: follow pagination, discover categories, and fetch detail pages concurrently."""
from __future__ import annotations

import difflib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple

from .exceptions import ScrapeError, WebScraperError
from .models import Book, Category
from .parse import find_next_page, parse_books, parse_categories, parse_detail

log = logging.getLogger(__name__)

Fetch = Callable[[str], str]


def crawl(fetch: Fetch, start_url: str, max_pages: Optional[int] = None,
          on_page: Optional[Callable[[int, str, int], None]] = None,
          parse: Callable[[str, str], List[Any]] = parse_books,
          next_page: Callable[[str, str], Optional[str]] = find_next_page,
          noun: str = "books") -> Iterator[Any]:
    """Yield books from `start_url` onwards.

    fetch:      function that takes a URL and returns its HTML (injected so tests need no network)
    max_pages:  stop after this many pages (None = until there is no next page)
    on_page:    optional progress callback(page_number, url, items_found)
    parse / next_page: how to read a page; defaults are for the books site (see webscraper.sites)
    """
    url: Optional[str] = start_url
    seen = set()
    page_no = 0
    while url and url not in seen and (max_pages is None or page_no < max_pages):
        seen.add(url)  # protects against a 'next' link that loops back
        page_no += 1
        html = fetch(url)
        items = parse(html, url)
        if not items and page_no == 1:
            raise ScrapeError(f"no {noun} found on the first page ({url}) - the site layout may have changed")
        if on_page:
            on_page(page_no, url, len(items))
        yield from items
        url = next_page(html, url)


def discover_categories(fetch: Fetch, index_url: str) -> List[Category]:
    categories = parse_categories(fetch(index_url), index_url)
    if not categories:
        raise ScrapeError(f"no categories found at {index_url}")
    return categories


def resolve_categories(names: Sequence[str], available: Sequence[Category]) -> List[Category]:
    """Match user-typed names (case-insensitive) to real categories, with helpful errors."""
    by_name = {c.name.lower(): c for c in available}
    chosen: List[Category] = []
    for name in names:
        match = by_name.get(name.strip().lower())
        if match is None:
            close = difflib.get_close_matches(name.strip().lower(), list(by_name), n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(by_name[c].name for c in close)}?" if close else ""
            raise ScrapeError(f"unknown category {name!r}.{hint}")
        if match not in chosen:
            chosen.append(match)
    return chosen


@dataclass
class EnrichResult:
    books: List[Book]
    failures: List[Tuple[str, str]] = field(default_factory=list)  # (url, reason)
    interrupted: bool = False


def enrich(books: Sequence[Book], fetch: Fetch, workers: int = 4,
           on_progress: Optional[Callable[[int, int], None]] = None) -> EnrichResult:
    """Visit every book's own page and fill in category, UPC, description, stock count...

    Pages are fetched concurrently (the HTTP client still enforces the polite delay). A book whose
    page fails keeps its listing data and is reported in ``failures`` - one bad page never aborts
    the run. Order is preserved. Ctrl+C stops cleanly and returns what is done so far.
    """
    total = len(books)
    results: List[Book] = list(books)
    failures: List[Tuple[str, str]] = []
    interrupted = False

    def work(index: int) -> Tuple[int, Optional[Book], Optional[str]]:
        book = books[index]
        try:
            return index, replace(book, **parse_detail(fetch(book.url))), None
        except WebScraperError as exc:
            return index, None, str(exc)

    executor = ThreadPoolExecutor(max_workers=max(workers, 1))
    futures = [executor.submit(work, i) for i in range(total)]
    done = 0
    try:
        for future in futures:
            index, book, error = future.result()
            done += 1
            if book is not None:
                results[index] = book
            else:
                failures.append((books[index].url, error or "unknown error"))
                log.warning("details failed for %s: %s", books[index].url, error)
            if on_progress:
                on_progress(done, total)
    except KeyboardInterrupt:
        interrupted = True
        log.warning("interrupted - keeping %d/%d detail pages fetched so far", done, total)
    finally:
        executor.shutdown(wait=not interrupted, cancel_futures=True)
    return EnrichResult(results, failures, interrupted)
