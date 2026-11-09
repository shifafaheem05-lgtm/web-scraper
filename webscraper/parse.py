"""Pure HTML parsing functions (no network), so they are easy to test."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .exceptions import ScrapeError
from .models import Book, Category

log = logging.getLogger(__name__)

RATINGS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

__all__ = ["ScrapeError", "find_next_page", "parse_books", "parse_categories", "parse_detail",
           "parse_price", "parse_rating", "parse_total_results"]


def parse_price(text: str) -> float:
    """'£51.77' or 'Â£51.77' (wrongly decoded) -> 51.77"""
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    if not match:
        raise ScrapeError(f"could not read price from {text!r}")
    return float(match.group())


def parse_rating(tag: Any) -> int:
    """<p class="star-rating Three"> -> 3. Unknown or missing -> 0."""
    if tag is None:
        return 0
    for cls in tag.get("class", []):
        if cls.lower() in RATINGS:
            return RATINGS[cls.lower()]
    return 0


def parse_books(html: str, page_url: str) -> List[Book]:
    """Extract every book listed on one catalogue page. Malformed cards are skipped, not fatal."""
    soup = BeautifulSoup(html, "html.parser")
    books: List[Book] = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        price_tag = card.select_one("p.price_color")
        if link is None or price_tag is None:
            log.warning("skipping a book card without title or price on %s", page_url)
            continue
        title = str(link.get("title") or link.get_text(strip=True)).strip()
        try:
            price = parse_price(price_tag.get_text())
        except ScrapeError as exc:
            log.warning("skipping %r: %s", title, exc)
            continue
        availability = card.select_one("p.availability")
        in_stock = bool(availability and "in stock" in availability.get_text(" ", strip=True).lower())
        image = card.select_one("img")
        books.append(Book(
            title=title,
            price=price,
            rating=parse_rating(card.select_one("p.star-rating")),
            in_stock=in_stock,
            url=urljoin(page_url, str(link.get("href", ""))),
            image_url=urljoin(page_url, str(image.get("src", ""))) if image else "",
        ))
    return books


def find_next_page(html: str, page_url: str) -> Optional[str]:
    """Absolute URL of the 'next' page, or None on the last page."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one("li.next a") or soup.select_one("a[rel=next]")
    if link and link.get("href"):
        return urljoin(page_url, str(link["href"]))
    return None


def parse_total_results(html: str) -> Optional[int]:
    """'<strong>1000</strong> results' -> 1000 (None if the page has no such counter)."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.select_one("form.form-horizontal strong")
    if tag and tag.get_text(strip=True).isdigit():
        return int(tag.get_text(strip=True))
    return None


def parse_categories(html: str, page_url: str) -> List[Category]:
    """The category list from the site's sidebar (the top-level 'Books' entry is excluded)."""
    soup = BeautifulSoup(html, "html.parser")
    return [Category(name=a.get_text(strip=True), url=urljoin(page_url, str(a["href"])))
            for a in soup.select("div.side_categories ul ul li a[href]")]


def _optional_price(text: Optional[str]) -> Optional[float]:
    try:
        return parse_price(text or "")
    except ScrapeError:
        return None


def parse_detail(html: str) -> Dict[str, Any]:
    """Extra fields from a single book page, as a dict ready for ``dataclasses.replace``.

    Raises ScrapeError if the page has no product information table (wrong page / layout change).
    """
    soup = BeautifulSoup(html, "html.parser")
    table: Dict[str, str] = {}
    for row in soup.select("table.table-striped tr"):
        head, cell = row.find("th"), row.find("td")
        if head and cell:
            table[head.get_text(strip=True)] = cell.get_text(" ", strip=True)
    if not table:
        raise ScrapeError("no product information table found - the page layout may have changed")

    availability = table.get("Availability", "")
    stock = re.search(r"\((\d+)\s+available\)", availability)
    reviews = table.get("Number of reviews", "")
    crumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    description = soup.select_one("#product_description ~ p")

    detail: Dict[str, Any] = {
        "upc": table.get("UPC") or None,
        "product_type": table.get("Product Type") or None,
        "price_excl_tax": _optional_price(table.get("Price (excl. tax)")),
        "price_incl_tax": _optional_price(table.get("Price (incl. tax)")),
        "tax": _optional_price(table.get("Tax")),
        "stock_quantity": int(stock.group(1)) if stock else None,
        "num_reviews": int(reviews) if reviews.isdigit() else None,
        "category": crumbs[-2] if len(crumbs) >= 4 else None,
        "description": description.get_text(" ", strip=True) if description else None,
    }
    if availability:
        detail["in_stock"] = "in stock" in availability.lower()
    return detail
