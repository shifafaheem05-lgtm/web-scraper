"""Command line interface.

    webscraper scrape --max-pages 3 --min-rating 4 -o output/books.csv
    webscraper categories
    webscraper stats output/books.csv
    webscraper history --db output/history.db "light in the"

Older invocations without a sub-command (``python -m webscraper --max-pages 3``) still work.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .cache import DiskCache
from .client import USER_AGENT, PoliteSession
from .crawl import discover_categories
from .exceptions import WebScraperError
from .export import FORMATS, infer_format, load_books, save
from .filters import SORT_KEYS, Filters
from .pipeline import START_URL, ScrapeOptions, run, site_index
from .stats import format_summary, summarize
from .storage import HistoryStore, format_changes

COMMANDS = ("scrape", "categories", "stats", "history")
CACHE_DIR = ".webscraper_cache"
log = logging.getLogger("webscraper")


# --------------------------------------------------------------------------- parsers
def _network_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("network")
    g.add_argument("--url", default=START_URL, help="first catalogue page (default: %(default)s)")
    g.add_argument("--delay", type=float, default=1.0, help="minimum seconds between requests (default 1.0)")
    g.add_argument("--timeout", type=float, default=15.0, help="seconds before a request gives up (default 15)")
    g.add_argument("--retries", type=int, default=3, help="retries on temporary errors (default 3)")
    g.add_argument("--user-agent", default=USER_AGENT, help="User-Agent header to send")
    g.add_argument("--proxy", help="proxy URL, e.g. http://127.0.0.1:8080")
    g.add_argument("--ignore-robots", action="store_true", help="do not check robots.txt (not recommended)")
    g.add_argument("--no-cache", action="store_true", help="always download, never use the on-disk cache")
    g.add_argument("--cache-dir", default=CACHE_DIR, help="cache folder (default %(default)s)")
    g.add_argument("--cache-ttl", type=float, default=24.0, help="hours a cached page stays valid (default 24)")
    g.add_argument("--clear-cache", action="store_true", help="empty the cache before starting")
    return p


def _logging_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("logging")
    g.add_argument("-v", "--verbose", action="store_true", help="debug output (every request)")
    g.add_argument("-q", "--quiet", action="store_true", help="only warnings and errors")
    return p


def build_parser() -> argparse.ArgumentParser:
    parent = [_network_parser(), _logging_parser()]
    root = argparse.ArgumentParser(
        prog="webscraper",
        description="Scrape book data from books.toscrape.com (a site made for practising scraping).")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = root.add_subparsers(dest="command", metavar="{scrape,categories,stats,history}")

    s = sub.add_parser("scrape", parents=parent, help="scrape books (default command)",
                       description="Crawl the catalogue, filter, and export.")
    sc = s.add_argument_group("what to scrape")
    sc.add_argument("--max-pages", type=int, default=3, help="pages per start URL (default 3; the site has 50)")
    sc.add_argument("--all-pages", action="store_true", help="follow every page (overrides --max-pages)")
    sc.add_argument("--category", action="append", default=[], metavar="NAME",
                    help="scrape only this category (repeatable); see `webscraper categories`")
    sc.add_argument("--all-categories", action="store_true", help="scrape every category")
    sc.add_argument("--details", action="store_true",
                    help="also visit each book's page: category, UPC, description, stock count, reviews, tax")
    sc.add_argument("--workers", type=int, default=4, help="parallel workers for --details (default 4)")
    fl = s.add_argument_group("filtering and ordering")
    fl.add_argument("--min-rating", type=int, default=0, choices=range(0, 6), metavar="0-5",
                    help="keep books with at least this many stars")
    fl.add_argument("--max-rating", type=int, default=5, choices=range(0, 6), metavar="0-5",
                    help="keep books with at most this many stars")
    fl.add_argument("--min-price", type=float, help="keep books priced at or above this value")
    fl.add_argument("--max-price", type=float, help="keep books priced at or below this value")
    fl.add_argument("--in-stock", action="store_true", help="keep only books that are in stock")
    fl.add_argument("--search", metavar="TEXT", help="keep books whose title (or description/category) contains TEXT")
    fl.add_argument("--sort", choices=sorted(SORT_KEYS), help="sort the results")
    fl.add_argument("--desc", action="store_true", help="sort descending")
    fl.add_argument("--limit", type=int, help="keep only the first N results")
    out = s.add_argument_group("output")
    out.add_argument("-o", "--output", action="append", default=[], metavar="FILE",
                     help=f"output file; repeatable. Format comes from the extension ({', '.join(FORMATS)})")
    out.add_argument("--format", choices=FORMATS, help="force the output format (default: from extension, else csv)")
    out.add_argument("--db", metavar="FILE", help="SQLite history file: track new books and price/stock changes between runs")
    out.add_argument("--config", metavar="FILE", help="TOML file providing defaults for any option on this page")

    c = sub.add_parser("categories", parents=parent, help="list the site's categories")
    c.set_defaults(command="categories")

    st = sub.add_parser("stats", parents=[_logging_parser()], help="statistics for an exported file",
                        description="Summarise a CSV/JSON/JSONL file written by `scrape`.")
    st.add_argument("file")
    st.add_argument("--json", action="store_true", help="print machine-readable JSON")

    h = sub.add_parser("history", parents=[_logging_parser()], help="price history from a --db file")
    h.add_argument("--db", required=True, metavar="FILE")
    h.add_argument("search", nargs="?", default="", help="part of a title (default: all books)")
    h.add_argument("--limit", type=int, default=10, help="max books to show (default 10)")
    return root


# --------------------------------------------------------------------------- helpers
def _setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    for handler in list(log.handlers):
        if getattr(handler, "_webscraper_cli", False):
            log.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler._webscraper_cli = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s" if verbose else "%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO)
    log.propagate = False


def _load_config(path: str) -> Dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - Python < 3.11
        import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise WebScraperError(f"cannot read config file {path}: {exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise WebScraperError(f"invalid TOML in {path}: {exc}") from None
    section = data.get("scrape", data)
    return {str(k).replace("-", "_"): v for k, v in section.items() if not isinstance(v, dict)}


def _normalize_argv(argv: Sequence[str]) -> List[str]:
    """No sub-command given (old style)? Treat it as `scrape`."""
    args = list(argv)
    if not args or (args[0] not in COMMANDS and args[0] not in ("-h", "--help", "--version")):
        args.insert(0, "scrape")
    return args


def _make_client(args: argparse.Namespace) -> PoliteSession:
    cache = None
    if not args.no_cache:
        cache = DiskCache(args.cache_dir, ttl=args.cache_ttl * 3600)
        if args.clear_cache:
            log.info("Cache cleared (%d pages)", cache.clear())
    return PoliteSession(delay=args.delay, timeout=args.timeout, respect_robots=not args.ignore_robots,
                         user_agent=args.user_agent, retries=args.retries, cache=cache, proxy=args.proxy)


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit cannot be negative")
    if args.min_rating > args.max_rating:
        parser.error("--min-rating cannot be higher than --max-rating")
    for flag in ("min_price", "max_price"):
        if getattr(args, flag) is not None and getattr(args, flag) < 0:
            parser.error(f"--{flag.replace('_', '-')} cannot be negative")
    if args.min_price is not None and args.max_price is not None and args.min_price > args.max_price:
        parser.error("--min-price cannot be higher than --max-price")


# --------------------------------------------------------------------------- commands
def cmd_scrape(args: argparse.Namespace) -> int:
    client = _make_client(args)
    options = ScrapeOptions(
        url=args.url,
        max_pages=None if args.all_pages else args.max_pages,
        categories=tuple(args.category),
        all_categories=args.all_categories,
        details=args.details,
        workers=args.workers,
        filters=Filters(args.min_rating, args.max_rating, args.min_price, args.max_price, args.in_stock, args.search),
        sort=args.sort,
        descending=args.desc,
        limit=args.limit,
    )
    result = run(options, client.get)

    outputs = args.output or [f"output/books.{args.format or 'csv'}"]
    for target in outputs:
        fmt = args.format or infer_format(target) or "csv"
        save(result.kept, target, fmt)

    stats = summarize(result.kept)
    print(f"\nScraped {len(result.scraped)} books, kept {stats['count']} after filters -> {', '.join(outputs)}")
    if stats["count"]:
        print(format_summary(stats))
    else:
        print("Nothing matched your filters.")
    if args.details and result.failures:
        print(f"\n{len(result.failures)} detail page(s) could not be read (those books keep their listing data).")
    print(f"Requests: {client.requests_made} made, {client.cache_hits} served from cache")

    if args.db:
        with HistoryStore(args.db) as store:
            first = store.run_count() == 0
            print("\n" + format_changes(store.record(result.kept), first_run=first))
    if result.interrupted:
        print("\nInterrupted - partial results were saved.", file=sys.stderr)
        return 130
    if result.incomplete:
        print("\nWarning: a page could not be fetched, so the results are incomplete (what was found is saved). "
              "Run again - cached pages are reused.", file=sys.stderr)
        return 1
    return 0


def cmd_categories(args: argparse.Namespace) -> int:
    client = _make_client(args)
    for category in discover_categories(client.get, site_index(args.url)):
        print(category.name)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    stats = summarize(load_books(args.file))
    print(json.dumps(stats, indent=2, ensure_ascii=False) if args.json else format_summary(stats, top_categories=10))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        raise WebScraperError(f"history file {args.db} does not exist - create it with `scrape --db {args.db}`")
    with HistoryStore(args.db) as store:
        found = store.history(args.search, args.limit)
        print(f"{store.run_count()} run(s) recorded.")
    if not found:
        print("No matching books.")
    for title, url, points in found:
        print(f"\n{title}\n  {url}")
        for when, price, in_stock in points:
            print(f"  {when}  {price:>7.2f}  {'in stock' if in_stock else 'out of stock'}")
    return 0


HANDLERS = {"scrape": cmd_scrape, "categories": cmd_categories, "stats": cmd_stats, "history": cmd_history}


def _make_streams_safe() -> None:
    """A Windows console (or a pipe) using a legacy code page must not crash on titles like 'Café ’'."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - not every stream supports it; that is fine
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _make_streams_safe()
    parser = build_parser()
    raw = _normalize_argv(sys.argv[1:] if argv is None else argv)

    # A --config file supplies defaults; explicit command-line options still win.
    if raw[0] == "scrape" and any(a == "--config" or a.startswith("--config=") for a in raw):
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--config")
        known, _ = pre.parse_known_args(raw[1:])
        if known.config:
            try:
                config = _load_config(known.config)
            except WebScraperError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            scrape_parser = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices["scrape"]
            unknown = sorted(set(config) - {a.dest for a in scrape_parser._actions})
            if unknown:
                parser.error(f"unknown option(s) in {known.config}: {', '.join(unknown)}")
            for key in ("output", "category"):  # TOML allows a single string where a list is expected
                if isinstance(config.get(key), str):
                    config[key] = [config[key]]
            scrape_parser.set_defaults(**config)

    args = parser.parse_args(raw)
    _setup_logging(getattr(args, "verbose", False), getattr(args, "quiet", False))
    if args.command == "scrape":
        _validate(args, parser)
    try:
        return HANDLERS[args.command](args)
    except (WebScraperError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
