import json
import sqlite3
from contextlib import closing

import pytest

from webscraper import Book, ExportError
from webscraper.export import infer_format, load_books, save
from webscraper.report import build_html_report
from webscraper.storage import Changes, HistoryStore, format_changes


def book(i=1, **kw):
    data = dict(title=f"Book {i}", price=10.5 + i, rating=i % 5 + 1, in_stock=i % 2 == 0,
                url=f"https://x.test/b{i}", image_url=f"https://x.test/b{i}.jpg")
    data.update(kw)
    return Book(**data)


FULL = book(2, category="Travel", upc="u1", description="Line one, with comma\nand a newline", stock_quantity=7,
            num_reviews=3, price_excl_tax=11.5, price_incl_tax=12.5, tax=1.0, product_type="Books")


@pytest.mark.parametrize("name", ["b.csv", "b.json", "b.jsonl"])
def test_roundtrip_preserves_everything(tmp_path, name):
    books = [book(1), FULL, book(3, title="Ünïcode £ title")]
    path = save(books, tmp_path / "sub" / name)
    assert load_books(path) == books


def test_format_inference():
    assert infer_format("x.CSV") == "csv" and infer_format("x.ndjson") == "jsonl"
    assert infer_format("x.db") == "sqlite" and infer_format("x.txt") is None


def test_unknown_format_rejected(tmp_path):
    with pytest.raises(ValueError):
        save([book()], tmp_path / "b.xml", "xml")


def test_csv_blocks_formula_injection_but_roundtrips(tmp_path):
    evil = book(1, title='=HYPERLINK("http://evil","click")')
    path = save([evil], tmp_path / "e.csv")
    assert "'=HYPERLINK" in path.read_text(encoding="utf-8")
    assert load_books(path)[0].title == evil.title


def test_json_is_valid_utf8(tmp_path):
    path = save([book(1, title="café")], tmp_path / "b.json")
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "café"


def test_sqlite_export(tmp_path):
    path = save([book(1), FULL], tmp_path / "b.db")
    with closing(sqlite3.connect(path)) as con:
        rows = con.execute("SELECT title, price, in_stock, category FROM books ORDER BY title").fetchall()
    assert rows == [("Book 1", 11.5, 0, None), ("Book 2", 12.5, 1, "Travel")]
    save([book(1)], path)  # overwriting replaces the table instead of failing
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1


def test_xlsx_export(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = save([book(1), FULL], tmp_path / "b.xlsx")
    ws = openpyxl.load_workbook(path).active
    assert ws["A1"].value == "title" and ws["A3"].value == "Book 2" and ws.freeze_panes == "A2"


def test_html_report_escapes_and_blocks_javascript_links(tmp_path):
    nasty = book(1, title="<script>alert(1)</script>", url="javascript:alert(1)")
    page = build_html_report([nasty])
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert 'href="javascript:' not in page
    path = save([book(1), FULL], tmp_path / "r.html")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>") and "Book 2" in text and "Travel" in text


def test_html_report_handles_empty_input():
    assert "0" in build_html_report([])


def test_load_errors_are_friendly(tmp_path):
    with pytest.raises(ExportError, match="not a valid"):
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        load_books(tmp_path / "bad.json")
    with pytest.raises(ExportError, match="cannot read"):
        load_books(tmp_path / "x.txt")
    with pytest.raises(ExportError):
        load_books(tmp_path / "missing.csv")


# ---- history -----------------------------------------------------------------------------
def test_history_tracks_new_price_and_stock_changes(tmp_path):
    with HistoryStore(tmp_path / "h.db") as store:
        assert store.run_count() == 0
        first = store.record([book(1, price=10), book(2, price=20)])
        assert len(first.new) == 2 and first.total == 2

        second = store.record([book(1, price=12), book(2, price=20, in_stock=not book(2).in_stock), book(3)])
        assert [x.title for x in second.new] == ["Book 3"]
        assert [(c[0].title, c[1], c[2]) for c in second.price_changes] == [("Book 1", 10, 12)]
        assert [c[0].title for c in second.stock_changes] == ["Book 2"]

        third = store.record([book(1, price=12)])
        assert third.total == 0 and store.run_count() == 3

        title, url, points = store.history("book 1")[0]
        assert [p[1] for p in points] == [10, 12, 12]


def test_history_search_treats_wildcards_literally(tmp_path):
    with HistoryStore(tmp_path / "h.db") as store:
        store.record([book(1, title="100% Pure"), book(2, title="Other")])
        assert [h[0] for h in store.history("%")] == ["100% Pure"]
        assert store.history("zzz") == []


def test_format_changes():
    assert "first run" in format_changes(Changes(new=[book(1)]), first_run=True)
    assert "no changes" in format_changes(Changes())
    text = format_changes(Changes(price_changes=[(book(1), 10.0, 12.5)]))
    assert "Book 1: 10.00 -> 12.50" in text
