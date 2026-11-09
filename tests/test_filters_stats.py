import pytest

from webscraper import Book, Filters, apply_filters, sort_books
from webscraper.stats import format_summary, price_buckets, summarize


def b(title="T", price=10.0, rating=3, in_stock=True, **kw):
    return Book(title=title, price=price, rating=rating, in_stock=in_stock, url=f"https://x.test/{title}", **kw)


BOOKS = [b("Alpha", 51.77, 3), b("Beta", 53.74, 1, False), b("Gamma", 50.10, 1), b("Delta", 47.82, 4), b("Eps", 35.02, 5)]


def test_filters():
    assert len(apply_filters(BOOKS, min_rating=4)) == 2
    assert len(apply_filters(BOOKS, max_price=50)) == 2
    assert len(apply_filters(BOOKS, in_stock_only=True)) == 4
    assert len(apply_filters(BOOKS)) == 5


def test_extended_filters():
    assert [x.title for x in BOOKS if Filters(min_price=50).matches(x)] == ["Alpha", "Beta", "Gamma"]
    assert [x.title for x in BOOKS if Filters(max_rating=1).matches(x)] == ["Beta", "Gamma"]
    assert [x.title for x in BOOKS if Filters(search="DEL").matches(x)] == ["Delta"]


def test_search_covers_description_and_category_when_scraped():
    rich = b("Plain", description="A story about dragons", category="Fantasy")
    assert Filters(search="dragon").matches(rich)
    assert Filters(search="fantasy").matches(rich)
    assert not Filters(search="dragon").matches(b("Plain"))


def test_sorting():
    assert [x.title for x in sort_books(BOOKS, "price")][:2] == ["Eps", "Delta"]
    assert sort_books(BOOKS, "price", descending=True)[0].title == "Beta"
    assert [x.title for x in sort_books(BOOKS, "title")] == ["Alpha", "Beta", "Delta", "Eps", "Gamma"]
    assert sort_books(BOOKS, None) == BOOKS
    with pytest.raises(ValueError):
        sort_books(BOOKS, "colour")


def test_summary():
    s = summarize(BOOKS)
    assert s["count"] == 5 and s["in_stock"] == 4
    assert s["cheapest"] == "Eps" and s["most_expensive"] == "Beta"
    assert s["average_price"] == 47.69 and s["median_price"] == 50.10
    assert s["by_rating"] == {1: 2, 3: 1, 4: 1, 5: 1}
    assert "by_category" not in s
    assert summarize([]) == {"count": 0}


def test_summary_by_category():
    s = summarize([b("A", 10, category="X"), b("B", 20, category="X"), b("C", 5, category="Y")])
    assert s["by_category"] == {"X": {"count": 2, "average_price": 15.0}, "Y": {"count": 1, "average_price": 5.0}}


def test_price_buckets_cover_every_book():
    prices = [10.5, 12, 19.99, 25, 33, 59.99]
    buckets = price_buckets(prices)
    assert sum(n for _, n in buckets) == len(prices)
    assert price_buckets([]) == [] and price_buckets([7, 7]) == [("7-8", 2)]


def test_format_summary_is_readable():
    text = format_summary(summarize(BOOKS))
    assert "Books: 5" in text and "Cheapest: Eps" in text and "#" in text
    assert format_summary({"count": 0}) == "No books."
