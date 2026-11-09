"""A tiny on-disk HTTP cache so re-runs (and crashed runs) do not re-download pages."""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Union


class DiskCache:
    """Stores page bodies as files named after the SHA-256 of the URL.

    ttl: seconds a cached page stays valid (``None`` = forever, ``0`` = always stale).
    """

    def __init__(self, directory: Union[str, Path], ttl: Optional[float] = 24 * 3600) -> None:
        self.directory = Path(directory)
        self.ttl = ttl

    def _path(self, url: str) -> Path:
        return self.directory / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".html")

    def get(self, url: str) -> Optional[str]:
        path = self._path(url)
        try:
            if self.ttl is not None and time.time() - path.stat().st_mtime >= self.ttl:
                return None
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def set(self, url: str, text: str) -> None:
        """Write atomically so a crash or a parallel worker never leaves a half-written file."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self._path(url))
        except OSError:
            pass  # a cache that cannot be written must never break scraping

    def clear(self) -> int:
        """Delete every cached page; returns how many were removed."""
        removed = 0
        if self.directory.is_dir():
            for item in self.directory.glob("*.html"):
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
