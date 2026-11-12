import csv
import json
import sqlite3
from contextlib import closing
from urllib.parse import urlparse

import pytest

from tests.fakequotes import FakeQuotesSite
from tests.fakesite import FakeServer, FakeSite
from webscraper import Book, Filters, ScrapeOptions, WebScraperError, run
from webscraper.cli import main
from webscraper.demo import build_demo_page
from webscraper.export import load_books, save
from webscraper.sites import BOOKS, QUOTES, SITES, get_site
from webscraper.sites.quotes import parse_quotes

QBASE = "https://quotes.toscrape.com/page/1/"


@pytest.fixture
def qfetch():
    pages = FakeQuotesSite().build()
    return lambda url: pages[urlparse(url).path]


# ---- the site registry -------------------------------------------------------------------
def test_registry():
    assert set(SITES) == {"books", "quotes"} and get_site("quotes") is QUOTES and BOOKS.book_features
    with pytest.raises(WebScraperError, match="unknown site"):
        get_site("nope")


def test_parse_quotes():
    quotes = parse_quotes(FakeQuotesSite().build()["/page/1/"], QBASE)
    assert len(quotes) == 10
    first = quotes[0]
    assert first.text == "Quote number 1 about life" and first.author == "Albert Einstein"
    assert first.tags == ("life", "books") and first.author_url == "https://quotes.toscrape.com/author/Albert-Einstein"
    assert parse_quotes("<div class='quote'><span class='text'>no author</span></div>", QBASE) == []


# ---- the pipeline works for another site -------------------------------------------------
def test_pipeline_with_quotes(qfetch):
    result = run(ScrapeOptions(url=QBASE, max_pages=None), qfetch, QUOTES)
    assert len(result.scraped) == 25 and len(result.kept) == 25


def test_quotes_search_sort_limit(qfetch):
    opts = ScrapeOptions(url=QBASE, max_pages=None, filters=Filters(search="humor"), sort="author", limit=3)
    kept = run(opts, qfetch, QUOTES).kept
    assert len(kept) == 3 and all("humor" in " ".join(q.tags) or "humor" in q.text for q in kept)
    assert [q.author for q in kept] == sorted(q.author for q in kept)


def test_quotes_are_deduplicated():
    page = FakeQuotesSite().build()["/page/1/"].replace('href="/page/2/"', 'href="/page/1/"')
    # a looping "next" link must not repeat quotes
    assert len(run(ScrapeOptions(url=QBASE, max_pages=None), lambda u: page, QUOTES).scraped) == 10


def test_book_only_features_are_rejected_for_quotes(qfetch):
    with pytest.raises(WebScraperError, match="not available"):
        run(ScrapeOptions(url=QBASE, details=True), qfetch, QUOTES)


def test_default_site_is_still_books(memory_fetch):
    assert len(run(ScrapeOptions(max_pages=1), memory_fetch).scraped) == 20


# ---- CLI ---------------------------------------------------------------------------------
def quotes_cli(srv, tmp_path, *extra):
    return main(["scrape", "--site", "quotes", "--url", f"{srv.base}/page/1/", "--delay", "0", "--no-cache", *extra])


def test_cli_scrapes_quotes_to_every_format(tmp_path, capsys):
    with FakeServer(FakeQuotesSite()) as srv:
        outs = [tmp_path / n for n in ("q.csv", "q.json", "q.db", "q.html", "q.jsonl")]
        args = [x for o in outs for x in ("-o", str(o))]
        assert quotes_cli(srv, tmp_path, "--all-pages", *args) == 0
    text = capsys.readouterr().out
    assert "Scraped 25 quotes" in text and "Top authors" in text
    with open(outs[0], encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 25 and rows[0]["tags"] == "life; books" and list(rows[0]) == ["text", "author", "tags", "author_url"]
    assert json.loads(outs[1].read_text(encoding="utf-8"))[0]["tags"] == ["life", "books"]
    with closing(sqlite3.connect(outs[2])) as con:
        assert con.execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == 25
    page = outs[3].read_text(encoding="utf-8")
    assert "Quotes report" in page and "Albert Einstein" in page
    assert len(outs[4].read_text(encoding="utf-8").splitlines()) == 25


def test_cli_quotes_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "q.xlsx"
    with FakeServer(FakeQuotesSite()) as srv:
        assert quotes_cli(srv, tmp_path, "--max-pages", "1", "-o", str(out)) == 0
    ws = openpyxl.load_workbook(out).active
    assert ws["A1"].value == "text" and ws.max_row == 11 and ws.title == "Quotes"


def test_cli_quotes_empty_result_keeps_header(tmp_path):
    out = tmp_path / "q.csv"
    with FakeServer(FakeQuotesSite()) as srv:
        assert quotes_cli(srv, tmp_path, "--search", "zzzz", "-o", str(out)) == 0
    assert out.read_text(encoding="utf-8-sig").strip() == "text,author,tags,author_url"


@pytest.mark.parametrize("flags", [["--details"], ["--category", "x"], ["--min-rating", "3"], ["--max-price", "5"],
                                   ["--in-stock"], ["--db", "x.db"], ["--sort", "price"]])
def test_cli_rejects_book_only_options_for_quotes(tmp_path, capsys, flags):
    with FakeServer(FakeQuotesSite()) as srv:
        assert quotes_cli(srv, tmp_path, *flags, "-o", str(tmp_path / "q.csv")) == 1
    assert "Error:" in capsys.readouterr().err


def test_cli_categories_for_quotes_is_a_clean_error(capsys):
    assert main(["categories", "--site", "quotes"]) == 1
    assert "no categories" in capsys.readouterr().err


def test_cli_unknown_site_exits_2():
    with pytest.raises(SystemExit) as exc:
        main(["scrape", "--site", "nope"])
    assert exc.value.code == 2


def test_cli_sites_command(capsys):
    assert main(["sites"]) == 0
    out = capsys.readouterr().out
    assert "books" in out and "quotes" in out and "quotes.toscrape.com" in out


def test_generic_save_with_explicit_fields_and_empty_list(tmp_path):
    path = save([], tmp_path / "e.csv", fields=["a", "b"], table="things")
    assert path.read_text(encoding="utf-8-sig").strip() == "a,b"


# ---- demo page ---------------------------------------------------------------------------
def make_books(categories=True):
    return [Book(f"Book <{i}> & co", 10.0 + i, i % 5 + 1, i % 2 == 0, f"https://x.test/{i}",
                 category="Travel" if categories and i % 2 else ("Poetry" if categories else None),
                 stock_quantity=i, num_reviews=1, upc=f"u{i}") for i in range(12)]


def test_demo_page_real_vs_sample_labels():
    real = build_demo_page(make_books(), real=True)
    sample = build_demo_page(make_books(), real=False)
    assert "Real data." in real and "real scrape" in real and "Sample data" not in real
    assert "Sample data." in sample and "not real listings" in sample and "Real data." not in sample


def test_demo_page_is_complete_and_safe():
    page = build_demo_page(make_books())
    assert page.startswith("<!doctype html>") and "{{" not in page
    assert 'name="description"' in page and 'property="og:title"' in page      # SEO / link previews
    assert "Book &lt;1&gt; &amp; co" in page and "Book <1>" not in page         # scraped text is escaped
    assert 'id="cat"' in page and "Books per category" in page


def test_demo_page_without_categories_has_no_category_controls():
    page = build_demo_page(make_books(categories=False))
    assert 'id="cat"' not in page and "Books per category" not in page and "{{" not in page


def test_demo_page_needs_books():
    with pytest.raises(ValueError):
        build_demo_page([])


def test_cli_demo_command(tmp_path, capsys):
    data = save(make_books(), tmp_path / "b.csv")
    out = tmp_path / "docs" / "index.html"
    assert main(["demo", str(data), "-o", str(out)]) == 0
    assert "Real data." in out.read_text(encoding="utf-8") and "real scrape" in capsys.readouterr().out
    assert main(["demo", str(data), "-o", str(out), "--sample"]) == 0
    assert "Sample data." in out.read_text(encoding="utf-8")


def test_cli_demo_errors(tmp_path, capsys):
    assert main(["demo", str(tmp_path / "missing.csv")]) == 1
    empty = save([], tmp_path / "empty.csv")
    assert main(["demo", str(empty)]) == 1
    assert "Error:" in capsys.readouterr().err


def test_end_to_end_scrape_then_demo(tmp_path):
    with FakeServer(FakeSite(count=30)) as srv:
        csv_path = tmp_path / "books.csv"
        assert main(["scrape", "--url", srv.start_url, "--delay", "0", "--no-cache", "--all-pages", "--details",
                     "-o", str(csv_path)]) == 0
    assert len(load_books(csv_path)) == 30
    assert main(["demo", str(csv_path), "-o", str(tmp_path / "index.html")]) == 0
    assert "Books per category" in (tmp_path / "index.html").read_text(encoding="utf-8")
