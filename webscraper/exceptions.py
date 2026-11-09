"""Exception hierarchy. Catch ``WebScraperError`` to handle every error this package raises."""
from __future__ import annotations


class WebScraperError(Exception):
    """Base class for all errors raised by this package."""


class FetchError(WebScraperError):
    """A page could not be downloaded (network problem, HTTP error status...)."""


class RobotsDisallowed(FetchError):
    """robots.txt forbids fetching the URL (or could not be retrieved)."""


class ScrapeError(WebScraperError):
    """A page did not look like we expected (layout changed, wrong site...)."""


class ExportError(WebScraperError):
    """Results could not be written to / read from a file."""
