"""A polite, tested, feature-rich web scraper for the books.toscrape.com practice site."""
__version__ = "2.1.0"

from .crawl import crawl, enrich  # noqa: E402
from .exceptions import ExportError, FetchError, RobotsDisallowed, ScrapeError, WebScraperError  # noqa: E402
from .filters import Filters, apply_filters, sort_books  # noqa: E402
from .models import Book, Category  # noqa: E402
from .parse import find_next_page, parse_books, parse_detail  # noqa: E402
from .pipeline import ScrapeOptions, ScrapeResult, run  # noqa: E402

__all__ = [
    "Book", "Category", "ExportError", "FetchError", "Filters", "RobotsDisallowed", "ScrapeError",
    "ScrapeOptions", "ScrapeResult", "WebScraperError", "__version__", "apply_filters", "crawl",
    "enrich", "find_next_page", "parse_books", "parse_detail", "run", "sort_books",
]
