"""Adapter for https://books.toscrape.com (the default site)."""
from __future__ import annotations

from typing import Sequence

from ..filters import SORT_KEYS
from ..models import FIELDS, Book
from ..parse import find_next_page, parse_books
from ..stats import format_summary, summarize
from .base import Site

START_URL = "https://books.toscrape.com/catalogue/page-1.html"


def _summary(books: Sequence[Book]) -> str:
    return format_summary(summarize(books))


BOOKS = Site(
    name="books",
    description="books.toscrape.com: prices, ratings, stock, categories, detail pages, price history",
    start_url=START_URL,
    item_noun="books",
    table="books",
    parse_listing=parse_books,
    find_next=find_next_page,
    search_text=lambda b: " ".join(filter(None, (b.title, b.category, b.description))),
    sort_keys=dict(SORT_KEYS),
    columns=tuple(FIELDS),
    summarize=_summary,
    book_features=True,
)
