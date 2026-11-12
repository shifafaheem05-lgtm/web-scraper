"""Adapter for https://quotes.toscrape.com (a second practice site, to show the design is not tied to one site)."""
from __future__ import annotations

from collections import Counter
from dataclasses import fields
from typing import List, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Quote
from ..parse import find_next_page
from .base import Site

START_URL = "https://quotes.toscrape.com/page/1/"


def parse_quotes(html: str, page_url: str) -> List[Quote]:
    """Every quote on one page. Cards missing text or author are skipped."""
    soup = BeautifulSoup(html, "html.parser")
    quotes: List[Quote] = []
    for card in soup.select("div.quote"):
        text, author = card.select_one("span.text"), card.select_one("small.author")
        if text is None or author is None:
            continue
        link = card.select_one("a[href^='/author/']")
        quotes.append(Quote(
            text=text.get_text(strip=True).strip("“”\"").strip(),
            author=author.get_text(strip=True),
            tags=tuple(t.get_text(strip=True) for t in card.select("div.tags a.tag")),
            author_url=urljoin(page_url, str(link["href"])) if link else "",
        ))
    return quotes


def summarize(quotes: Sequence[Quote]) -> str:
    if not quotes:
        return "No quotes."
    authors = Counter(q.author for q in quotes)
    tags = Counter(t for q in quotes for t in q.tags)
    lines = [f"Quotes: {len(quotes)}  |  authors: {len(authors)}  |  distinct tags: {len(tags)}",
             "Top authors: " + ", ".join(f"{a} ({n})" for a, n in authors.most_common(5)),
             "Top tags: " + ", ".join(f"{t} ({n})" for t, n in tags.most_common(5))]
    return "\n".join(lines)


QUOTES = Site(
    name="quotes",
    description="quotes.toscrape.com: quotes with author and tags",
    start_url=START_URL,
    item_noun="quotes",
    table="quotes",
    parse_listing=parse_quotes,
    find_next=find_next_page,
    search_text=lambda q: " ".join((q.text, q.author, *q.tags)),
    sort_keys={"author": lambda q: q.author.lower(), "text": lambda q: q.text.lower(),
               "tags": lambda q: len(q.tags)},
    columns=tuple(f.name for f in fields(Quote)),
    summarize=summarize,
)
