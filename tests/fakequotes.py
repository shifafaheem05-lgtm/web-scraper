"""A fake quotes.toscrape.com with the same HTML structure (same interface as FakeSite, for FakeServer)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

AUTHORS = ["Albert Einstein", "Jane Austen", "Marilyn Monroe", "André Gide"]
TAGS = ["life", "love", "books", "humor", "change"]

CARD = """<div class="quote" itemscope itemtype="http://schema.org/CreativeWork">
<span class="text" itemprop="text">“{text}”</span>
<span>by <small class="author" itemprop="author">{author}</small><a href="/author/{slug}">(about)</a></span>
<div class="tags">Tags: {tags}</div></div>"""


@dataclass
class FakeQuotesSite:
    count: int = 25
    per_page: int = 10
    robots: Optional[str] = None
    quotes: List[Tuple[str, str, Tuple[str, ...]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for i in range(self.count):
            self.quotes.append((f"Quote number {i + 1} about {TAGS[i % 5]}", AUTHORS[i % len(AUTHORS)],
                                (TAGS[i % 5], TAGS[(i + 2) % 5])))

    def build(self) -> Dict[str, str]:
        pages: Dict[str, str] = {}
        n_pages = (self.count + self.per_page - 1) // self.per_page
        for p in range(1, n_pages + 1):
            chunk = self.quotes[(p - 1) * self.per_page: p * self.per_page]
            cards = "".join(CARD.format(
                text=t, author=a, slug=a.replace(" ", "-"),
                tags="".join(f'<a class="tag" href="/tag/{x}/page/1/">{x}</a>' for x in tags)) for t, a, tags in chunk)
            nxt = f'<li class="next"><a href="/page/{p + 1}/">Next <span>→</span></a></li>' if p < n_pages else ""
            pages[f"/page/{p}/"] = f'<html><body>{cards}<nav><ul class="pager">{nxt}</ul></nav></body></html>'
        return pages
