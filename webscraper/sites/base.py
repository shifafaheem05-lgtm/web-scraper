"""What a "site adapter" is: everything the pipeline needs to know about one website."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class Site:
    """Describes how to scrape one website.

    To support a new site, write the two parsing functions, describe the item as a dataclass
    with an ``as_dict()`` method, and register a ``Site`` in ``webscraper/sites/__init__.py``.
    """

    name: str                                              # used for --site NAME
    description: str
    start_url: str
    item_noun: str                                         # "books", "quotes" ... (for messages)
    table: str                                             # SQLite table name / file label
    parse_listing: Callable[[str, str], List[Any]]         # (html, page_url) -> items
    find_next: Callable[[str, str], Optional[str]]         # (html, page_url) -> next page URL or None
    search_text: Callable[[Any], str]                      # text that --search looks in
    sort_keys: Dict[str, Callable[[Any], Any]] = field(default_factory=dict)
    columns: Sequence[str] = ()                            # export columns (needed when no item was found)
    summarize: Callable[[Sequence[Any]], str] = lambda items: f"{len(items)} items"
    # Extras that only the books site has: categories, detail pages, price/rating filters, history.
    book_features: bool = False
