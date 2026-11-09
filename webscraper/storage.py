"""SQLite history: remember every run so price and stock changes can be tracked over time."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from .models import Book

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    book_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    first_seen_run INTEGER NOT NULL,
    last_seen_run INTEGER NOT NULL,
    price REAL NOT NULL,
    in_stock INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    url TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    price REAL NOT NULL,
    in_stock INTEGER NOT NULL,
    PRIMARY KEY (url, run_id)
);
"""


@dataclass
class Changes:
    """What changed compared with the previous time each book was seen."""
    new: List[Book] = field(default_factory=list)
    price_changes: List[Tuple[Book, float, float]] = field(default_factory=list)   # (book, old, new)
    stock_changes: List[Tuple[Book, bool, bool]] = field(default_factory=list)     # (book, old, new)

    @property
    def total(self) -> int:
        return len(self.new) + len(self.price_changes) + len(self.stock_changes)


class HistoryStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.executescript(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> HistoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def record(self, books: Sequence[Book]) -> Changes:
        """Store a run and return what is new / cheaper / dearer / back in stock since last seen."""
        changes = Changes()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.con:
            run_id = self.con.execute("INSERT INTO runs (started_at, book_count) VALUES (?, ?)",
                                      (now, len(books))).lastrowid
            for book in books:
                row = self.con.execute("SELECT price, in_stock FROM books WHERE url = ?", (book.url,)).fetchone()
                payload = json.dumps(book.as_dict(), ensure_ascii=False)
                if row is None:
                    changes.new.append(book)
                    self.con.execute("INSERT INTO books VALUES (?, ?, ?, ?, ?, ?, ?)",
                                     (book.url, book.title, run_id, run_id, book.price, int(book.in_stock), payload))
                else:
                    old_price, old_stock = row[0], bool(row[1])
                    if abs(old_price - book.price) > 1e-9:
                        changes.price_changes.append((book, old_price, book.price))
                    if old_stock != book.in_stock:
                        changes.stock_changes.append((book, old_stock, book.in_stock))
                    self.con.execute("UPDATE books SET title=?, last_seen_run=?, price=?, in_stock=?, data=? WHERE url=?",
                                     (book.title, run_id, book.price, int(book.in_stock), payload, book.url))
                self.con.execute("INSERT OR REPLACE INTO price_history VALUES (?, ?, ?, ?)",
                                 (book.url, run_id, book.price, int(book.in_stock)))
        return changes

    def run_count(self) -> int:
        return int(self.con.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def history(self, search: str, limit: int = 20) -> List[Tuple[str, str, List[Tuple[str, float, bool]]]]:
        """(title, url, [(run date, price, in_stock), ...]) for books whose title contains ``search``."""
        rows = self.con.execute(
            "SELECT url, title FROM books WHERE title LIKE ? ESCAPE '\\' ORDER BY title LIMIT ?",
            ("%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", limit)).fetchall()
        result = []
        for url, title in rows:
            points = self.con.execute(
                "SELECT r.started_at, h.price, h.in_stock FROM price_history h JOIN runs r ON r.id = h.run_id "
                "WHERE h.url = ? ORDER BY r.id", (url,)).fetchall()
            result.append((title, url, [(d, p, bool(s)) for d, p, s in points]))
        return result


def format_changes(changes: Changes, limit: int = 10, first_run: Optional[bool] = None) -> str:
    if first_run:
        return f"History: first run recorded ({len(changes.new)} books)."
    if not changes.total:
        return "History: no changes since the previous run."
    lines = [f"History: {len(changes.new)} new, {len(changes.price_changes)} price changes, "
             f"{len(changes.stock_changes)} stock changes since the previous run."]
    for book, old, new in changes.price_changes[:limit]:
        lines.append(f"  price  {book.title}: {old:.2f} -> {new:.2f}")
    for book, old, new in changes.stock_changes[:limit]:
        lines.append(f"  stock  {book.title}: {'in stock' if old else 'out of stock'} -> {'in stock' if new else 'out of stock'}")
    return "\n".join(lines)
