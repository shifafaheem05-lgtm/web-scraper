import json
import sqlite3
from contextlib import closing

import pytest

from tests.fakesite import FakeServer, FakeSite
from webscraper.cli import main


def scrape(server, tmp_path, *extra, command=("scrape",)):
    args = [*command, "--url", server.start_url, "--delay", "0", "--cache-dir", str(tmp_path / "cache"), *extra]
    return main(args)


def test_basic_scrape_writes_csv_and_prints_summary(server, tmp_path, capsys):
    out = tmp_path / "books.csv"
    assert scrape(server, tmp_path, "--max-pages", "2", "-o", str(out)) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 41
    text = capsys.readouterr().out
    assert "Scraped 40 books, kept 40" in text and "Price distribution" in text


def test_legacy_invocation_without_subcommand(server, tmp_path):
    out = tmp_path / "old.json"
    assert main(["--url", server.start_url, "--delay", "0", "--no-cache", "--max-pages", "1",
                 "--format", "json", "-o", str(out)]) == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 20


def test_filters_sort_limit_and_multiple_outputs(server, tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.jsonl"
    assert scrape(server, tmp_path, "--all-pages", "--min-rating", "4", "--in-stock", "--sort", "price", "--desc",
                  "--limit", "3", "-o", str(a), "-o", str(b)) == 0
    rows = [json.loads(line) for line in b.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3 and rows == sorted(rows, key=lambda r: -r["price"])
    assert a.exists()


def test_details_flag_adds_columns(server, tmp_path):
    out = tmp_path / "d.json"
    assert scrape(server, tmp_path, "--max-pages", "1", "--details", "--workers", "3", "-o", str(out)) == 0
    first = json.loads(out.read_text(encoding="utf-8"))[0]
    assert first["upc"] == "upc0001" and first["category"] == "Travel" and first["stock_quantity"]


def test_category_scrape_and_listing(server, tmp_path, capsys):
    out = tmp_path / "c.csv"
    assert scrape(server, tmp_path, "--category", "mystery", "--all-pages", "-o", str(out)) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 16
    capsys.readouterr()
    assert scrape(server, tmp_path, command=("categories",)) == 0
    assert capsys.readouterr().out.split() == ["Travel", "Mystery", "Poetry"]


def test_unknown_category_is_a_clean_error(server, tmp_path, capsys):
    assert scrape(server, tmp_path, "--category", "Mistery", "-o", str(tmp_path / "x.csv")) == 1
    assert "Did you mean: Mystery" in capsys.readouterr().err


def test_cache_makes_second_run_free(server, tmp_path, capsys):
    scrape(server, tmp_path, "--max-pages", "1", "-o", str(tmp_path / "1.csv"))
    hits = len(server.hits)
    scrape(server, tmp_path, "--max-pages", "1", "-o", str(tmp_path / "2.csv"))
    assert len(server.hits) == hits          # nothing downloaded: pages came from the cache
    assert "served from cache" in capsys.readouterr().out
    before = len(server.hits)
    scrape(server, tmp_path, "--max-pages", "1", "--no-cache", "-o", str(tmp_path / "3.csv"))
    assert len(server.hits) > before          # --no-cache really downloads again


def test_robots_blocks_with_clear_error(tmp_path, capsys):
    with FakeServer(FakeSite(count=3, robots="User-agent: *\nDisallow: /")) as srv:
        assert scrape(srv, tmp_path, "-o", str(tmp_path / "x.csv")) == 1
        assert "robots.txt" in capsys.readouterr().err
        assert scrape(srv, tmp_path, "--ignore-robots", "-o", str(tmp_path / "x.csv")) == 0


def test_history_db_reports_changes_between_runs(tmp_path, capsys):
    db = str(tmp_path / "h.db")
    site = FakeSite(count=4)
    with FakeServer(site) as srv:
        assert scrape(srv, tmp_path, "--no-cache", "--db", db, "-o", str(tmp_path / "o.csv")) == 0
        assert "first run recorded (4 books)" in capsys.readouterr().out
        site.books[0].price += 5          # the shop changes a price
        srv.pages = site.build()
        assert scrape(srv, tmp_path, "--no-cache", "--db", db, "-o", str(tmp_path / "o.csv")) == 0
        assert "1 price changes" in capsys.readouterr().out
        assert main(["history", "--db", db, "light story"]) == 0
        out = capsys.readouterr().out
        assert "2 run(s) recorded" in out and "10.00" in out and "15.00" in out


def test_stats_command(server, tmp_path, capsys):
    out = tmp_path / "s.csv"
    scrape(server, tmp_path, "--max-pages", "1", "-o", str(out))
    capsys.readouterr()
    assert main(["stats", str(out)]) == 0 and "Books: 20" in capsys.readouterr().out
    assert main(["stats", str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 20


def test_stats_on_missing_file_is_clean_error(tmp_path, capsys):
    assert main(["stats", str(tmp_path / "nope.csv")]) == 1
    assert "Error:" in capsys.readouterr().err


def test_history_on_missing_db(tmp_path, capsys):
    assert main(["history", "--db", str(tmp_path / "none.db")]) == 1


def test_config_file_supplies_defaults_but_cli_wins(server, tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text(f'[scrape]\nurl = "{server.start_url}"\ndelay = 0\nno-cache = true\nmax-pages = 1\n'
                   f'min-rating = 5\noutput = "{(tmp_path / "cfg.json").as_posix()}"\n', encoding="utf-8")
    assert main(["scrape", "--config", str(cfg)]) == 0
    rows = json.loads((tmp_path / "cfg.json").read_text(encoding="utf-8"))
    assert rows and all(r["rating"] == 5 for r in rows)
    assert main(["scrape", "--config", str(cfg), "--min-rating", "1", "--max-pages", "2"]) == 0
    assert len(json.loads((tmp_path / "cfg.json").read_text(encoding="utf-8"))) == 40


def test_bad_config(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("nonsense = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["scrape", "--config", str(bad)])
    assert exc.value.code == 2
    assert main(["scrape", "--config", str(tmp_path / "missing.toml")]) == 1


@pytest.mark.parametrize("flags", [["--max-pages", "0"], ["--workers", "0"], ["--min-rating", "5", "--max-rating", "2"],
                                   ["--min-price", "9", "--max-price", "3"], ["--limit", "-1"], ["--delay", "-1"],
                                   ["--min-rating", "9"]])
def test_invalid_arguments_exit_2(flags):
    with pytest.raises(SystemExit) as exc:
        main(["scrape", *flags])
    assert exc.value.code == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "webscraper 2." in capsys.readouterr().out


def test_empty_result_still_writes_file(server, tmp_path, capsys):
    out = tmp_path / "e.csv"
    assert scrape(server, tmp_path, "--max-pages", "1", "--search", "zzzz", "-o", str(out)) == 0
    assert out.exists() and "Nothing matched" in capsys.readouterr().out


def test_sqlite_output_via_extension(server, tmp_path):
    out = tmp_path / "o.db"
    scrape(server, tmp_path, "--max-pages", "1", "-o", str(out))
    with closing(sqlite3.connect(out)) as con:
        assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 20
