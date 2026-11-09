"""Filtering, searching and sorting of scraped books."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from .models import Book


@dataclass(frozen=True)
class Filters:
    min_rating: int = 0
    max_rating: int = 5
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    in_stock_only: bool = False
    search: Optional[str] = None   # case-insensitive text in title (and description/category if scraped)

    def matches(self, book: Book) -> bool:
        if not self.min_rating <= book.rating <= self.max_rating:
            return False
        if self.min_price is not None and book.price < self.min_price:
            return False
        if self.max_price is not None and book.price > self.max_price:
            return False
        if self.in_stock_only and not book.in_stock:
            return False
        if self.search:
            haystack = " ".join(filter(None, (book.title, book.category, book.description))).lower()
            if self.search.lower() not in haystack:
                return False
        return True


def apply_filters(books: Iterable[Book], min_rating: int = 0, max_price: Optional[float] = None,
                  in_stock_only: bool = False, **extra: object) -> List[Book]:
    """Convenience wrapper: ``apply_filters(books, min_rating=4, max_price=30, search="python")``."""
    flt = Filters(min_rating=min_rating, max_price=max_price, in_stock_only=in_stock_only, **extra)  # type: ignore[arg-type]
    return [b for b in books if flt.matches(b)]


SORT_KEYS: Dict[str, Callable[[Book], object]] = {
    "title": lambda b: b.title.lower(),
    "price": lambda b: b.price,
    "rating": lambda b: b.rating,
    "stock": lambda b: b.stock_quantity if b.stock_quantity is not None else -1,
    "reviews": lambda b: b.num_reviews if b.num_reviews is not None else -1,
}


def sort_books(books: Iterable[Book], key: Optional[str], descending: bool = False) -> List[Book]:
    if key is None:
        return list(books)
    if key not in SORT_KEYS:
        raise ValueError(f"cannot sort by {key!r}; choose from {', '.join(SORT_KEYS)}")
    return sorted(books, key=SORT_KEYS[key], reverse=descending)  # type: ignore[arg-type]
