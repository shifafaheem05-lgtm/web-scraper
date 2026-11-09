"""A polite HTTP client.

It identifies itself, retries temporary errors, rate-limits across threads, honours
``robots.txt`` (including ``Crawl-delay``), and can cache pages on disk.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__
from .cache import DiskCache
from .exceptions import FetchError, RobotsDisallowed
from .ratelimit import RateLimiter

log = logging.getLogger(__name__)

USER_AGENT = f"WebScraper/{__version__} (learning project; +https://github.com/shifafaheem05-lgtm/web-scraper)"

__all__ = ["USER_AGENT", "FetchError", "PoliteSession", "RobotsDisallowed"]


class PoliteSession:
    """Download pages politely. ``get(url)`` returns the page HTML as text and is thread-safe."""

    def __init__(self, delay: float = 1.0, timeout: float = 15.0, respect_robots: bool = True,
                 session: Optional[requests.Session] = None, user_agent: str = USER_AGENT,
                 retries: int = 3, cache: Optional[DiskCache] = None,
                 proxy: Optional[str] = None) -> None:
        self.delay = max(delay, 0.0)
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self.retries = max(retries, 0)
        self.cache = cache
        self.proxy = proxy

        self.requests_made = 0
        self.cache_hits = 0

        self._limiter = RateLimiter(self.delay)
        self._robots: Dict[str, RobotFileParser] = {}
        self._robots_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._shared_session = session
        if session is not None:
            self._configure(session)
        self._local = threading.local()

    # -- session handling -------------------------------------------------------------
    def _configure(self, session: requests.Session) -> None:
        session.headers["User-Agent"] = self.user_agent
        retry = Retry(total=self.retries, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",))
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        if self.proxy:
            session.proxies.update({"http": self.proxy, "https": self.proxy})

    @property
    def session(self) -> requests.Session:
        """The session for the current thread (requests.Session is not guaranteed thread-safe)."""
        if self._shared_session is not None:
            return self._shared_session
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._configure(sess)
            self._local.session = sess
        return sess

    def _count(self, attribute: str) -> None:
        with self._counter_lock:
            setattr(self, attribute, getattr(self, attribute) + 1)

    # -- robots.txt -------------------------------------------------------------------
    def _load_robots(self, root: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            self._limiter.wait()
            resp = self.session.get(f"{root}/robots.txt", timeout=self.timeout)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            elif resp.status_code >= 500:
                log.warning("robots.txt on %s returned %s; treating the site as off-limits", root, resp.status_code)
                parser.parse(["User-agent: *", "Disallow: /"])
            else:
                parser.parse([])  # 404 etc. -> no robots.txt -> everything allowed
        except requests.RequestException as exc:
            log.warning("could not read robots.txt on %s (%s); treating the site as off-limits", root, exc)
            parser.parse(["User-agent: *", "Disallow: /"])
        crawl_delay = parser.crawl_delay(self.user_agent)
        if crawl_delay:
            log.info("robots.txt asks for a %ss crawl delay; slowing down", crawl_delay)
            self._limiter.raise_interval(float(crawl_delay))
        return parser

    def allowed(self, url: str) -> bool:
        """May we fetch ``url`` according to robots.txt?"""
        if not self.respect_robots:
            return True
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            parser = self._robots.get(root)
            if parser is None:
                parser = self._robots[root] = self._load_robots(root)
        return parser.can_fetch(self.user_agent, url)

    # -- fetching ---------------------------------------------------------------------
    def get(self, url: str) -> str:
        if self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                self._count("cache_hits")
                log.debug("cache hit %s", url)
                return cached
        if not self.allowed(url):
            raise RobotsDisallowed(
                f"robots.txt does not allow fetching {url} (or it could not be read; use --ignore-robots to skip the check)")
        self._limiter.wait()
        log.debug("GET %s", url)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"could not fetch {url}: {exc}") from None
        self._count("requests_made")
        # A server that does not declare a charset makes `requests` guess ISO-8859-1, which
        # turns '£' into 'Â£'. HTML on the modern web is UTF-8, so assume that.
        content_type = str(getattr(resp, "headers", {}).get("content-type", "")).lower()
        if "charset" not in content_type:
            resp.encoding = "utf-8"
        text = resp.text
        if self.cache is not None:
            self.cache.set(url, text)
        return text
