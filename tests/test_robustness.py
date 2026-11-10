"""Problems real users hit: flaky networks, Windows consoles, Excel, locked files."""
import io
import sys
from urllib.parse import urlparse

import pytest

from tests.fakesite import FakeServer, FakeSite
from webscraper import Book, FetchError, ScrapeOptions, run
from webscraper.cli import main
from webscraper.export import load_books, save


def test_network_drop_mid_crawl_keeps_earlier_pages(site):
    pages = site.build()

    def fetch(url):
        if url.endswith("page-2.html"):
            raise FetchError("connection reset")
        return pages[urlparse(url).path]
    result = run(ScrapeOptions(max_pages=None), fetch)
    assert len(result.scraped) == 20 and result.incomplete


def test_failure_on_the_very_first_page_is_still_an_error():
    def fetch(url):
        raise FetchError("no internet")
    with pytest.raises(FetchError):
        run(ScrapeOptions(), fetch)


def test_one_failing_category_does_not_lose_the_others(site):
    pages = site.build()

    def fetch(url):
        if "mystery_3" in url:
            raise FetchError("boom")
        return pages[urlparse(url).path]
    result = run(ScrapeOptions(all_categories=True, max_pages=None), fetch)
    assert result.incomplete and len(result.scraped) == 30   # Travel + Poetry survived


def test_cli_saves_partial_results_and_exits_1_on_mid_crawl_failure(tmp_path, capsys):
    with FakeServer(FakeSite()) as srv:
        del srv.pages["/catalogue/page-2.html"]          # the site "breaks" after page 1
        out = tmp_path / "partial.csv"
        rc = main(["scrape", "--url", srv.start_url, "--delay", "0", "--no-cache", "--all-pages", "-o", str(out)])
    assert rc == 1 and len(load_books(out)) == 20
    assert "incomplete" in capsys.readouterr().err


def test_csv_has_utf8_bom_so_excel_reads_accents(tmp_path):
    path = save([Book("Café ’Noir’ £5", 5.0, 3, True, "https://x.test/1")], tmp_path / "b.csv")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert load_books(path)[0].title == "Café ’Noir’ £5"
    (tmp_path / "plain.csv").write_bytes(path.read_bytes()[3:])      # a BOM-less file still loads
    assert load_books(tmp_path / "plain.csv")[0].title == "Café ’Noir’ £5"


def test_xlsx_survives_control_characters_in_scraped_text(tmp_path):
    pytest.importorskip("openpyxl")
    path = save([Book("Bad\x0bTitle\x00", 5.0, 3, True, "https://x.test/1", description="a\x1fb")], tmp_path / "b.xlsx")
    assert path.exists()


def test_non_ascii_titles_do_not_crash_a_legacy_console(tmp_path, monkeypatch):
    path = save([Book("Café ’Noir’ …", 5.0, 3, True, "https://x.test/1")], tmp_path / "b.json")
    ascii_out = io.TextIOWrapper(io.BytesIO(), encoding="ascii")   # like a cp1252/ASCII Windows pipe
    monkeypatch.setattr(sys, "stdout", ascii_out)
    assert main(["stats", str(path)]) == 0
    ascii_out.flush()
    assert b"Caf" in ascii_out.buffer.getvalue()


def test_unwritable_history_db_is_a_clean_error(server, tmp_path, capsys):
    rc = main(["scrape", "--url", server.start_url, "--delay", "0", "--no-cache", "--max-pages", "1",
               "-o", str(tmp_path / "o.csv"), "--db", str(tmp_path)])      # a directory, not a file
    assert rc == 1 and "Error:" in capsys.readouterr().err


def test_output_path_that_cannot_be_written_is_a_clean_error(server, tmp_path, capsys):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    rc = main(["scrape", "--url", server.start_url, "--delay", "0", "--no-cache", "--max-pages", "1",
               "-o", str(blocker / "sub" / "o.csv")])                         # parent is a file
    assert rc == 1 and "Error:" in capsys.readouterr().err
