"""Registry of supported websites. Add yours here (see ``base.Site``)."""
from __future__ import annotations

from typing import Dict

from ..exceptions import ScrapeError
from .base import Site
from .books import BOOKS
from .quotes import QUOTES

SITES: Dict[str, Site] = {site.name: site for site in (BOOKS, QUOTES)}


def get_site(name: str) -> Site:
    try:
        return SITES[name]
    except KeyError:
        raise ScrapeError(f"unknown site {name!r}; choose from: {', '.join(SITES)}") from None


__all__ = ["BOOKS", "QUOTES", "SITES", "Site", "get_site"]
