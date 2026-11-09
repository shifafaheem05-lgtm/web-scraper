"""Summary statistics."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence, Tuple

from .models import Book

_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]


def price_buckets(prices: Sequence[float], target: int = 6) -> List[Tuple[str, int]]:
    """Histogram bins with 'nice' widths (1, 2, 5, 10, 20...), about ``target`` of them."""
    if not prices:
        return []
    low, high = min(prices), max(prices)
    step = next((s for s in _STEPS if (high - low) / s <= target), _STEPS[-1])
    start = int(low // step * step)
    counts: Counter[int] = Counter(int((p - start) // step) for p in prices)
    return [(f"{start + i * step:g}-{start + (i + 1) * step:g}", counts.get(i, 0))
            for i in range(max(counts) + 1)]


def summarize(books: Sequence[Book]) -> Dict[str, Any]:
    if not books:
        return {"count": 0}
    prices = [b.price for b in books]
    cheapest = min(books, key=lambda b: b.price)
    priciest = max(books, key=lambda b: b.price)
    summary: Dict[str, Any] = {
        "count": len(books),
        "average_price": round(sum(prices) / len(prices), 2),
        "median_price": round(statistics.median(prices), 2),
        "cheapest": cheapest.title,
        "cheapest_price": cheapest.price,
        "most_expensive": priciest.title,
        "most_expensive_price": priciest.price,
        "in_stock": sum(b.in_stock for b in books),
        "average_rating": round(sum(b.rating for b in books) / len(books), 2),
        "by_rating": dict(sorted(Counter(b.rating for b in books).items())),
        "price_buckets": price_buckets(prices),
    }
    groups: Dict[str, List[float]] = defaultdict(list)
    for b in books:
        if b.category:
            groups[b.category].append(b.price)
    if groups:
        summary["by_category"] = {
            name: {"count": len(vals), "average_price": round(sum(vals) / len(vals), 2)}
            for name, vals in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        }
    return summary


def format_summary(stats: Dict[str, Any], top_categories: int = 5) -> str:
    """Human-readable multi-line summary for the terminal."""
    if not stats.get("count"):
        return "No books."
    lines = [
        f"Books: {stats['count']}  |  in stock: {stats['in_stock']}  |  average rating: {stats['average_rating']}",
        f"Price: average {stats['average_price']}, median {stats['median_price']}",
        f"Cheapest: {stats['cheapest']} ({stats['cheapest_price']})",
        f"Most expensive: {stats['most_expensive']} ({stats['most_expensive_price']})",
        f"Books per rating: {stats['by_rating']}",
    ]
    width = max((n for _, n in stats["price_buckets"]), default=1) or 1
    lines.append("Price distribution:")
    for label, n in stats["price_buckets"]:
        lines.append(f"  {label:>9} | {'#' * round(30 * n / width):<30} {n}")
    cats = stats.get("by_category")
    if cats:
        lines.append(f"Top categories (of {len(cats)}):")
        for name, info in list(cats.items())[:top_categories]:
            lines.append(f"  {name}: {info['count']} books, average price {info['average_price']}")
    return "\n".join(lines)
