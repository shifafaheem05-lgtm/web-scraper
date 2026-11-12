"""Writing results to files (CSV, JSON, JSON Lines, SQLite, Excel, HTML) and reading them back."""
from __future__ import annotations

import csv
import dataclasses
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Union

from .exceptions import ExportError
from .models import FIELDS, Book
from .report import build_generic_report, build_html_report

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


_ILLEGAL_XLSX = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _restore(value: str) -> str:
    return value[1:] if value.startswith("'") and value[1:].startswith(_FORMULA_PREFIXES) else value


class _Layout(NamedTuple):
    """Which columns to write and what to call the table (differs per site)."""
    fields: List[str]
    table: str


def _flat(value: Any) -> Any:
    """Lists (e.g. a quote's tags) become 'a; b; c' in flat formats such as CSV and Excel."""
    return "; ".join(map(str, value)) if isinstance(value, (list, tuple)) else value


def _save_csv(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    # utf-8-sig = UTF-8 with a BOM, so Excel on Windows shows 'Café' instead of 'CafÃ©'
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=layout.fields)
        writer.writeheader()
        for item in items:
            writer.writerow({k: _neutralize(_flat(v)) for k, v in item.as_dict().items()})


def _save_json(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([i.as_dict() for i in items], fh, indent=2, ensure_ascii=False)


def _save_jsonl(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item.as_dict(), ensure_ascii=False) + "\n")


def _sql_type(column: str) -> str:
    if column.startswith("price") or column == "tax":
        return "REAL"
    if column in ("rating", "in_stock", "stock_quantity", "num_reviews"):
        return "INTEGER"
    return "TEXT"


def _save_sqlite(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    table = re.sub(r"\W", "_", layout.table)
    columns = ", ".join(f"{name} {_sql_type(name)}" for name in layout.fields)
    key = ", PRIMARY KEY (url)" if "url" in layout.fields else ""
    con = sqlite3.connect(path)
    try:
        with con:
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(f"CREATE TABLE {table} ({columns}{key})")
            con.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({', '.join('?' * len(layout.fields))})",
                            [tuple(_flat(i.as_dict()[f]) for f in layout.fields) for i in items])
    finally:
        con.close()


def _save_xlsx(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ExportError('Excel export needs openpyxl: pip install "webscraper[excel]"') from None
    wb = Workbook()
    ws = wb.active
    assert ws is not None  # a new Workbook always has an active sheet
    ws.title = layout.table.capitalize()
    ws.append(layout.fields)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for item in items:
        row = (_flat(item.as_dict()[f]) for f in layout.fields)
        ws.append([_neutralize(_ILLEGAL_XLSX.sub("", v) if isinstance(v, str) else v) for v in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {"title": 45, "description": 60, "url": 50, "image_url": 40, "text": 80, "author_url": 40}
    for i, name in enumerate(layout.fields, start=1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(name, 16)
    wb.save(path)


def _save_html(items: Sequence[Any], path: Path, layout: _Layout) -> None:
    if items and not isinstance(items[0], Book) or (not items and layout.table != "books"):
        page = build_generic_report(items, layout.fields, f"{layout.table.capitalize()} report")
    else:
        page = build_html_report(items)
    path.write_text(page, encoding="utf-8")


_SAVERS: Dict[str, Callable[[Sequence[Any], Path, _Layout], None]] = {
    "csv": _save_csv, "json": _save_json, "jsonl": _save_jsonl,
    "sqlite": _save_sqlite, "xlsx": _save_xlsx, "html": _save_html,
}


def save(items: Sequence[Any], path: PathLike, fmt: Optional[str] = None, table: Optional[str] = None,
         fields: Optional[Sequence[str]] = None) -> Path:
    """Write scraped items to ``path``. ``fmt`` defaults to what the file extension implies.

    Books are the default. For other item types the columns come from the dataclass fields
    (pass ``fields`` and ``table`` to be explicit, e.g. when the list may be empty).
    """
    path = Path(path)
    fmt = fmt or infer_format(path) or "csv"
    if fmt not in _SAVERS:
        raise ValueError(f"format must be one of: {', '.join(FORMATS)}")
    if fields is None:
        fields = [f.name for f in dataclasses.fields(items[0])] if items and not isinstance(items[0], Book) else FIELDS
    layout = _Layout(list(fields), table or ("books" if list(fields) == FIELDS else "items"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _SAVERS[fmt](items, path, layout)
    except (OSError, sqlite3.Error) as exc:
        raise ExportError(f"could not write {path}: {exc}") from None
    return path


def load_books(path: PathLike) -> List[Book]:
    """Read books back from a CSV, JSON or JSON Lines file written by :func:`save`."""
    path = Path(path)
    fmt = infer_format(path)
    try:
        if fmt == "csv":
            with open(path, newline="", encoding="utf-8-sig") as fh:
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
