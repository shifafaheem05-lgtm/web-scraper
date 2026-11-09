import bs4
import pytest

from tests.fakesite import FakeSite
from webscraper import ScrapeError, find_next_page, parse_books, parse_detail
from webscraper.parse import parse_categories, parse_price, parse_rating, parse_total_results

BASE = "https://books.toscrape.com/catalogue/page-1.html"


@pytest.fixture
def pages():
    return FakeSite(count=45).build()


def test_parse_books_extracts_all_fields(pages):
    books = parse_books(pages["/catalogue/page-1.html"], BASE)
    assert len(books) == 20
    first = books[0]
    assert first.title == "Light Story 1"
    assert (first.price, first.rating, first.in_stock) == (10.0, 1, True)
    assert first.url == "https://books.toscrape.com/catalogue/light-story-1_1/index.html"
    assert first.image_url == "https://books.toscrape.com/media/light-story-1_1.jpg"


def test_out_of_stock_detected(pages):
    books = parse_books(pages["/catalogue/page-1.html"], BASE)
    assert [b.in_stock for b in books][:7] == [True] * 5 + [False] + [True]


def test_title_comes_from_attribute_not_truncated_text(pages):
    assert "..." not in parse_books(pages["/catalogue/page-1.html"], BASE)[0].title


def test_price_variants():
    assert parse_price("£51.77") == 51.77
    assert parse_price("Â£50.10") == 50.10  # mis-decoded pound sign
    assert parse_price("12") == 12.0
    with pytest.raises(ScrapeError):
        parse_price("free")


def test_rating():
    tag = bs4.BeautifulSoup('<p class="star-rating Five"></p>', "html.parser").p
    assert parse_rating(tag) == 5
    assert parse_rating(None) == 0
    assert parse_rating(bs4.BeautifulSoup('<p class="star-rating"></p>', "html.parser").p) == 0


def test_card_with_unreadable_price_is_skipped_not_fatal():
    """Regression: one bad price used to raise and abort the whole crawl."""
    site = FakeSite(count=5, bad_price_ids={3})
    books = parse_books(site.build()["/catalogue/page-1.html"], BASE)
    assert len(books) == 4
    assert all("Story 3" not in b.title for b in books)


def test_card_missing_pieces_is_skipped():
    html = "<article class='product_pod'><p>broken</p></article>"
    assert parse_books(html, BASE) == []


def test_next_page(pages):
    assert find_next_page(pages["/catalogue/page-1.html"], BASE) == "https://books.toscrape.com/catalogue/page-2.html"
    assert find_next_page(pages["/catalogue/page-3.html"], BASE) is None


def test_total_results(pages):
    assert parse_total_results(pages["/catalogue/page-1.html"]) == 45
    assert parse_total_results("<html></html>") is None


def test_categories(pages):
    cats = parse_categories(pages["/index.html"], "https://books.toscrape.com/index.html")
    assert [c.name for c in cats] == ["Travel", "Mystery", "Poetry"]   # 'Books' root excluded
    assert cats[0].url == "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"


def test_detail_page(pages):
    book = FakeSite(count=45).books[0]
    detail = parse_detail(pages[f"/catalogue/{book.slug}/index.html"])
    assert detail["upc"] == "upc0001"
    assert detail["category"] == "Travel"
    assert detail["stock_quantity"] == book.stock
    assert detail["num_reviews"] == 1
    assert detail["price_incl_tax"] == book.price and detail["tax"] == 0.0
    assert detail["description"].startswith("A tale about light")
    assert detail["in_stock"] is True


def test_detail_page_out_of_stock_and_no_description(pages):
    site = FakeSite(count=45)
    sold_out = site.books[5]
    detail = parse_detail(pages[f"/catalogue/{sold_out.slug}/index.html"])
    assert detail["in_stock"] is False and detail["stock_quantity"] is None
    no_desc = site.books[8]
    assert parse_detail(pages[f"/catalogue/{no_desc.slug}/index.html"])["description"] is None


def test_detail_page_wrong_layout_raises():
    with pytest.raises(ScrapeError):
        parse_detail("<html><body>nothing</body></html>")
