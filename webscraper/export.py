"""Writing results to files (CSV, JSON, JSON Lines, SQLite, Excel, HTML) and reading them back."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from .exceptions import ExportError
from .models import FIELDS, Book
from .report import build_html_report

PathLike = Union[str, Path]

EXTENSIONS: Dict[str, str] = {
    ".csv": "csv", ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
    ".db": "sqlite", ".sqlite": "sqlite", ".sqlite3": "sqlite", ".xlsx": "xlsx",
    ".html": "html", ".htm": "html",
}
FORMATS: List[str] = sorted(set(EXTENSIONS.values()))
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def infer_format(path: PathLike) -> Optional[str]:
    """Format implied by a file extension, or None if unrecognised."""
    return EXTENSIONS.get(Path(path).suffix.lower())


def _neutralize(value: Any) -> Any:
    """Stop spreadsheet formula injection: a scraped title like '=HYPERLINK(...)' becomes plain text."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _restore(value: str) -> str:
    return value[1:] if value.startswith("'") and value[1:].startswith(_FORMULA_PREFIXES) else value


def _save_csv(books: Sequence[Book], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for b in books:
            writer.writerow({k: _neutralize(v) for k, v in b.as_dict().items()})


def _save_json(books: Sequence[Book], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([b.as_dict() for b in books], fh, indent=2, ensure_ascii=False)


def _save_jsonl(books: Sequence[Book], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for b in books:
            fh.write(json.dumps(b.as_dict(), ensure_ascii=False) + "\n")


def _sql_type(column: str) -> str:
    if column.startswith("price") or column == "tax":
        return "REAL"
    if column in ("rating", "in_stock", "stock_quantity", "num_reviews"):
        return "INTEGER"
    return "TEXT"


def _save_sqlite(books: Sequence[Book], path: Path) -> None:
    columns = ", ".join(f"{name} {_sql_type(name)}" for name in FIELDS)
    con = sqlite3.connect(path)
    try:
        with con:
            con.execute("DROP TABLE IF EXISTS books")
            con.execute(f"CREATE TABLE books ({columns}, PRIMARY KEY (url))")
            con.executemany(f"INSERT OR REPLACE INTO books VALUES ({', '.join('?' * len(FIELDS))})",
                            [tuple(b.as_dict()[f] for f in FIELDS) for b in books])
    finally:
        con.close()


def _save_xlsx(books: Sequence[Book], path: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ExportError('Excel export needs openpyxl: pip install "webscraper[excel]"') from None
    wb = Workbook()
    ws = wb.active
    assert ws is not None  # a new Workbook always has an active sheet
    ws.title = "Books"
    ws.append(FIELDS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for b in books:
        ws.append([_neutralize(b.as_dict()[f]) for f in FIELDS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {"title": 45, "description": 60, "url": 50, "image_url": 40}
    for i, name in enumerate(FIELDS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(name, 16)
    wb.save(path)


def _save_html(books: Sequence[Book], path: Path) -> None:
    path.write_text(build_html_report(books), encoding="utf-8")


_SAVERS: Dict[str, Callable[[Sequence[Book], Path], None]] = {
    "csv": _save_csv, "json": _save_json, "jsonl": _save_jsonl,
    "sqlite": _save_sqlite, "xlsx": _save_xlsx, "html": _save_html,
}


def save(books: Sequence[Book], path: PathLike, fmt: Optional[str] = None) -> Path:
    """Write ``books`` to ``path``. ``fmt`` defaults to what the file extension implies."""
    path = Path(path)
    fmt = fmt or infer_format(path) or "csv"
    if fmt not in _SAVERS:
        raise ValueError(f"format must be one of: {', '.join(FORMATS)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _SAVERS[fmt](books, path)
    except OSError as exc:
        raise ExportError(f"could not write {path}: {exc}") from None
    return path


def load_books(path: PathLike) -> List[Book]:
    """Read books back from a CSV, JSON or JSON Lines file written by :func:`save`."""
    path = Path(path)
    fmt = infer_format(path)
    try:
        if fmt == "csv":
            with open(path, newline="", encoding="utf-8") as fh:
                return [Book.from_dict({k: _restore(v) if isinstance(v, str) else v for k, v in row.items()})
                        for row in csv.DictReader(fh)]
        if fmt == "json":
            return [Book.from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))]
        if fmt == "jsonl":
            return [Book.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise ExportError(f"could not read {path}: {exc}") from None
    except (KeyError, ValueError, TypeError) as exc:
        raise ExportError(f"{path} is not a valid books file: {exc!r}") from None
    raise ExportError(f"cannot read {path}: use a .csv, .json or .jsonl file")
