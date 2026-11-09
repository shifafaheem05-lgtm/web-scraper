"""A thread-safe rate limiter: guarantees a minimum gap between request *starts*."""
from __future__ import annotations

import threading
import time
from typing import Callable


class RateLimiter:
    """Hands out request slots at least ``interval`` seconds apart, even across threads.

    Concurrency therefore hides network latency but never makes the scraper hit a server
    faster than the configured delay.
    """

    def __init__(self, interval: float = 1.0, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = max(float(interval), 0.0)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def raise_interval(self, interval: float) -> None:
        """Increase (never decrease) the gap, e.g. to honour a robots.txt ``Crawl-delay``."""
        with self._lock:
            self.interval = max(self.interval, float(interval))

    def wait(self) -> float:
        """Block until this caller's slot arrives. Returns the seconds slept."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.interval
        delay = slot - now
        if delay > 0:
            self._sleep(delay)
        return max(delay, 0.0)
