# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-11-13

### Added
- Site adapters (`webscraper/sites/`): the pipeline, exports and CLI are no longer tied to one website. New `--site` option and `sites` command.
- Second built-in site: quotes.toscrape.com (`--site quotes`) with search, sort and limit, and every export format.
- `demo` command: builds a self-contained, SEO-ready demo page (meta description, Open Graph tags) from a scraped file, labelled as a real scrape or as sample data.
- Generic HTML report for non-book items.

### Changed
- `ScrapeOptions.url` defaults to the chosen site's start page; `crawl()` accepts `parse`/`next_page` functions.
- `export.save()` accepts `table` and `fields`, so any dataclass items can be exported.

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
- A network error halfway through a crawl threw away every page already scraped; the pages collected so far are now saved (exit code 1, with a warning).
- Titles with accents or curly quotes could crash the program on a Windows console/pipe using a legacy code page.
- CSV files showed garbled accents (`CafÃ©`) when opened in Excel on Windows; they are now written with a UTF-8 BOM.
- Excel export crashed on scraped text containing control characters.
- A locked or unwritable output file or history database produced a Python traceback instead of a clear error.
- `urllib3>=1.26` is now declared (older versions don't support the retry settings used).
- `robots.txt` fetches now go through the rate limiter, like every other request.

## [1.0.0]
- Initial version: multi-page crawl, filters, CSV/JSON export, polite HTTP client, 19 tests.
