"""A fake books.toscrape.com: same HTML structure, served from memory (optionally over loopback HTTP)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Set, Tuple

WORDS = ["Light", "Velvet", "Soumission", "Objects", "Attic", "Mesaerion", "Himalayas", "Garden", "Shadow", "Harbor"]
RATINGS = ["One", "Two", "Three", "Four", "Five"]

LISTING_CARD = """<li class="col-xs-6 col-sm-4 col-md-3 col-lg-3"><article class="product_pod">
<div class="image_container"><a href="{href}"><img src="{img}" alt="{title}" class="thumbnail"></a></div>
<p class="star-rating {rating}"><i class="icon-star"></i></p>
<h3><a href="{href}" title="{title}">{short}</a></h3>
<div class="product_price"><p class="price_color">{price}</p>
<p class="instock availability"><i class="icon-ok"></i> {stock} </p></div></article></li>"""

DETAIL = """<html><body><ul class="breadcrumb"><li><a href="../../index.html">Home</a></li>
<li><a href="../category/books_1/index.html">Books</a></li>{crumb}<li class="active">{title}</li></ul>
<article class="product_page"><div id="product_description" class="sub-header"><h2>Product Description</h2></div>{desc}
<table class="table table-striped"><tr><th>UPC</th><td>{upc}</td></tr><tr><th>Product Type</th><td>Books</td></tr>
<tr><th>Price (excl. tax)</th><td>{price}</td></tr><tr><th>Price (incl. tax)</th><td>{price}</td></tr>
<tr><th>Tax</th><td>£0.00</td></tr><tr><th>Availability</th><td>{avail}</td></tr>
<tr><th>Number of reviews</th><td>{reviews}</td></tr></table></article></body></html>"""


@dataclass
class FakeBook:
    id: int
    title: str
    price: float
    rating: int
    stock: int
    category: str
    description: Optional[str]

    @property
    def slug(self) -> str:
        return f"{self.title.lower().replace(' ', '-').replace(',', '')}_{self.id}"


@dataclass
class FakeSite:
    count: int = 45
    per_page: int = 20
    categories: Tuple[str, ...] = ("Travel", "Mystery", "Poetry")
    robots: Optional[str] = None            # None -> robots.txt is a 404
    broken_details: Set[int] = field(default_factory=set)
    bad_price_ids: Set[int] = field(default_factory=set)
    books: List[FakeBook] = field(default_factory=list)

    def __post_init__(self) -> None:
        for i in range(self.count):
            self.books.append(FakeBook(
                id=i + 1,
                title=f"{WORDS[i % len(WORDS)]} Story {i + 1}",
                price=round(10 + (i * 7.31) % 45, 2),
                rating=i % 5 + 1,
                stock=0 if i % 6 == 5 else 3 + i % 20,
                category=self.categories[i % len(self.categories)],
                description=None if i % 9 == 8 else f"A tale about {WORDS[i % len(WORDS)].lower()} (book {i + 1}).",
            ))

    # -- html builders ----------------------------------------------------------------
    def _card(self, b: FakeBook, prefix: str) -> str:
        price = "N/A" if b.id in self.bad_price_ids else f"£{b.price:.2f}"
        return LISTING_CARD.format(href=f"{prefix}{b.slug}/index.html", img=f"{prefix}../media/{b.slug}.jpg",
                                   title=b.title, short=b.title[:14] + "...", rating=RATINGS[b.rating - 1],
                                   price=price, stock="In stock" if b.stock else "Out of stock")

    def _listing(self, books: List[FakeBook], page: int, base: str, prefix: str, total: int) -> str:
        pages = max((len(books) + self.per_page - 1) // self.per_page, 1)
        chunk = books[(page - 1) * self.per_page: page * self.per_page]
        nxt = f'<li class="next"><a href="page-{page + 1}.html">next</a></li>' if page < pages else ""
        cats = "".join(f'<li><a href="catalogue/category/books/{c.lower()}_{n}/index.html">\n {c}\n</a></li>'
                       for n, c in enumerate(self.categories, start=2))
        side = (f'<div class="side_categories"><ul class="nav"><li><a href="catalogue/category/books_1/index.html">Books</a>'
                f"<ul>{cats}</ul></li></ul></div>")
        return (f'<html><body>{side}<form class="form-horizontal"><strong>{total}</strong> results</form>'
                f'<ol class="row">{"".join(self._card(b, prefix) for b in chunk)}</ol><ul class="pager">{nxt}</ul></body></html>')

    def build(self) -> Dict[str, str]:
        """path -> html for every page of the site."""
        pages: Dict[str, str] = {}
        pages["/index.html"] = self._listing([], 1, "", "catalogue/", len(self.books))
        n_pages = (len(self.books) + self.per_page - 1) // self.per_page
        for p in range(1, n_pages + 1):
            pages[f"/catalogue/page-{p}.html"] = self._listing(self.books, p, "", "", len(self.books))
        for n, cat in enumerate(self.categories, start=2):
            members = [b for b in self.books if b.category == cat]
            base = f"/catalogue/category/books/{cat.lower()}_{n}"
            cat_pages = max((len(members) + self.per_page - 1) // self.per_page, 1)
            for p in range(1, cat_pages + 1):
                name = "index.html" if p == 1 else f"page-{p}.html"
                pages[f"{base}/{name}"] = self._listing(members, p, "", "../../../", len(members))
        for b in self.books:
            if b.id in self.broken_details:
                pages[f"/catalogue/{b.slug}/index.html"] = "<html><body><p>oops</p></body></html>"
                continue
            desc = f"<p>{b.description}</p>" if b.description else ""
            pages[f"/catalogue/{b.slug}/index.html"] = DETAIL.format(
                crumb=f'<li><a href="x">{b.category}</a></li>', title=b.title, desc=desc, upc=f"upc{b.id:04d}",
                price=f"£{b.price:.2f}", avail=f"In stock ({b.stock} available)" if b.stock else "Out of stock",
                reviews=b.id % 4)
        return pages


class FakeServer:
    """Serve a FakeSite on 127.0.0.1 (random port) in a background thread; counts requests."""

    def __init__(self, site: FakeSite, flaky_once: Optional[Set[str]] = None) -> None:
        self.site = site
        self.pages = site.build()
        self.hits: List[str] = []
        self.flaky_once = set(flaky_once or ())
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.hits.append(self.path)
                if self.path == "/robots.txt":
                    if outer.site.robots is None:
                        return self._send(404, "not found")
                    return self._send(200, outer.site.robots)
                if self.path in outer.flaky_once:
                    outer.flaky_once.discard(self.path)
                    return self._send(503, "try again")
                body = outer.pages.get(self.path)
                if body is None:
                    return self._send(404, "not found")
                self._send(200, body)

            def _send(self, status: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html")   # no charset on purpose, like the real site
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> FakeServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    @property
    def start_url(self) -> str:
        return f"{self.base}/catalogue/page-1.html"

    def book_hits(self) -> int:
        return sum(1 for h in self.hits
                   if h.startswith("/catalogue/") and h.endswith("/index.html") and h.count("/") == 3)
