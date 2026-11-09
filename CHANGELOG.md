# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-11-09

### Added
- `--details`: visit each book's page for category, UPC, description, stock count, review count, product type and tax.
- Concurrent detail fetching (`--workers`) with a thread-safe rate limiter.
- Category scraping (`--category`, `--all-categories`) and the `categories` command.
- On-disk page cache with TTL (`--no-cache`, `--cache-dir`, `--cache-ttl`, `--clear-cache`).
- Export to JSON Lines, SQLite, Excel and a self-contained HTML report; several `-o` outputs per run.
- Filters `--min-price`, `--max-rating`, `--search`; `--sort`, `--desc`, `--limit`.
- Richer statistics (median, price histogram, per-category averages) and the `stats` command.
- SQLite history (`--db`) that reports new books and price/stock changes; `history` command.
- TOML config file (`--config`), `--proxy`, `--user-agent`, `--timeout`, `--retries`, `-v/-q` logging.
- `robots.txt` `Crawl-delay` support.
- Packaging (`pyproject.toml`, `webscraper` command, typed package), GitHub Actions CI, Dockerfile, Makefile.
- Sub-command CLI; the old `python -m scraper --max-pages 3` style still works (as `python -m webscraper ...`).

### Changed
- Package renamed from `scraper` to `webscraper` (avoids clashing with other packages).
- If `robots.txt` cannot be retrieved (5xx / network error) the site is now treated as off-limits instead of fully allowed.
- Charset handling: UTF-8 is assumed only when the server does not declare a charset.
- Progress is reported through `logging` instead of `print`.

### Fixed
- One book card with an unreadable price aborted the whole crawl (the README already promised malformed items were skipped).
- `Ctrl+C` discarded everything scraped so far; partial results are now saved (exit code 130).
- CSV/Excel exports were vulnerable to spreadsheet formula injection from scraped titles.
- `robots.txt` fetches now go through the rate limiter, like every other request.

## [1.0.0]
- Initial version: multi-page crawl, filters, CSV/JSON export, polite HTTP client, 19 tests.
