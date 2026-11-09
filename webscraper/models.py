"""Data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Callable, Dict, List, Mapping, Optional, TypeVar

T = TypeVar("T")


def _optional(convert: Callable[[Any], T], value: Any) -> Optional[T]:
    """Convert ``value`` unless it is None/empty (as it is when read back from a CSV file)."""
    if value is None or value == "":
        return None
    return convert(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


@dataclass(frozen=True)
class Book:
    """One book. The first six fields come from the listing page; the rest need ``--details``."""

    title: str
    price: float
    rating: int          # 1-5 stars (0 = unknown)
    in_stock: bool
    url: str
    image_url: str = ""
    category: Optional[str] = None
    upc: Optional[str] = None
    description: Optional[str] = None
    stock_quantity: Optional[int] = None
    num_reviews: Optional[int] = None
    price_excl_tax: Optional[float] = None
    price_incl_tax: Optional[float] = None
    tax: Optional[float] = None
    product_type: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Book:
        """Rebuild a Book from loosely-typed data (JSON values or CSV strings)."""
        return cls(
            title=str(data["title"]),
            price=float(data["price"]),
            rating=int(float(data.get("rating") or 0)),
            in_stock=_to_bool(data.get("in_stock", False)),
            url=str(data.get("url", "")),
            image_url=str(data.get("image_url") or ""),
            category=_optional(str, data.get("category")),
            upc=_optional(str, data.get("upc")),
            description=_optional(str, data.get("description")),
            stock_quantity=_optional(lambda v: int(float(v)), data.get("stock_quantity")),
            num_reviews=_optional(lambda v: int(float(v)), data.get("num_reviews")),
            price_excl_tax=_optional(float, data.get("price_excl_tax")),
            price_incl_tax=_optional(float, data.get("price_incl_tax")),
            tax=_optional(float, data.get("tax")),
            product_type=_optional(str, data.get("product_type")),
        )


FIELDS: List[str] = [f.name for f in fields(Book)]


@dataclass(frozen=True)
class Category:
    name: str
    url: str
