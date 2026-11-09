"""A self-contained HTML report (no external files, safe against HTML injection)."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from .models import Book
from .stats import summarize

_CSS = """
:root{--bg:#f7f7f5;--fg:#1c1c1a;--muted:#6b6b66;--card:#fff;--line:#e2e2dd;--accent:#2a6f6b}
@media(prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--card:#1f1f1d;--line:#34342f;--accent:#58b5ae}}
*{box-sizing:border-box}body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,sans-serif}main{max-width:1100px;margin:auto}h1{margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile,.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.tile b{display:block;font-size:1.5rem}.tile span{color:var(--muted);font-size:.85rem}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin:12px 0}
.bar{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:.85rem}.track{flex:1}.bar i{display:block;height:10px;
background:var(--accent);border-radius:3px;min-width:2px}.bar em{flex:0 0 64px;font-style:normal;color:var(--muted)}
.bar span{flex:0 0 28px;text-align:right}
input{width:100%;padding:9px 12px;margin:12px 0 8px;border:1px solid var(--line);border-radius:8px;
background:var(--card);color:var(--fg);font:inherit}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{cursor:pointer;user-select:none;color:var(--muted);font-size:.8rem;text-transform:uppercase}
td.t{white-space:normal;min-width:240px}a{color:var(--accent)}
"""

_JS = """
const q=document.getElementById('q'),tb=document.querySelector('tbody'),rows=[...tb.rows];
q.addEventListener('input',()=>{const s=q.value.toLowerCase();rows.forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(s))});
document.querySelectorAll('th').forEach((th,i)=>{let asc=true;th.addEventListener('click',()=>{
const num=th.dataset.n==='1';rows.sort((a,b)=>{const x=a.cells[i].dataset.v,y=b.cells[i].dataset.v;
return(num?x-y:x.localeCompare(y))*(asc?1:-1)});asc=!asc;rows.forEach(r=>tb.appendChild(r))})});
"""


def _safe_url(url: str) -> str:
    """Only http(s) links are clickable; a hostile 'javascript:' URL becomes '#'."""
    return url if url.lower().startswith(("http://", "https://")) else "#"


def _bars(items: Sequence[Tuple[Any, int]]) -> str:
    top = max((n for _, n in items), default=1) or 1
    return "".join(
        f'<div class="bar"><em>{html.escape(str(label))}</em>'
        f'<div class="track"><i style="width:{max(n / top * 100, 1):.0f}%"></i></div><span>{n}</span></div>'
        for label, n in items)


def build_html_report(books: Sequence[Book], title: str = "Book scrape report",
                      stats: Optional[Dict[str, Any]] = None) -> str:
    stats = stats if stats is not None else summarize(books)
    esc = html.escape
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not stats.get("count"):
        tiles = '<div class="tile"><b>0</b><span>books</span></div>'
        panels = ""
    else:
        tiles = "".join(f'<div class="tile"><b>{esc(str(v))}</b><span>{esc(k)}</span></div>' for k, v in (
            ("books", stats["count"]), ("average price", stats["average_price"]),
            ("median price", stats["median_price"]), ("in stock", stats["in_stock"]),
            ("average rating", stats["average_rating"])))
        ratings = [(f"{r} star", n) for r, n in stats["by_rating"].items()]
        panels = (f'<div class="panel"><h3>Ratings</h3>{_bars(ratings)}</div>'
                  f'<div class="panel"><h3>Price distribution</h3>{_bars(stats["price_buckets"])}</div>')
        if stats.get("by_category"):
            top = [(k, v["count"]) for k, v in list(stats["by_category"].items())[:8]]
            panels += f'<div class="panel"><h3>Top categories</h3>{_bars(top)}</div>'

    def cell(value: Any, numeric: bool = False, cls: str = "") -> str:
        text = "" if value is None else str(value)
        data = text if not numeric else (text or "0")
        return f'<td{f" class={cls}" if cls else ""} data-v="{esc(data.lower() if not numeric else data)}">{esc(text)}</td>'

    body = "".join(
        "<tr>"
        f'<td class="t" data-v="{esc(b.title.lower())}"><a href="{esc(_safe_url(b.url))}" rel="noopener noreferrer">{esc(b.title)}</a></td>'
        + cell(b.category) + cell(f"{b.price:.2f}", True) + cell(b.rating, True)
        + cell("yes" if b.in_stock else "no") + cell(b.stock_quantity, True) + cell(b.num_reviews, True)
        + "</tr>" for b in books)
    head = "".join(f'<th data-n="{n}">{esc(h)}</th>' for h, n in (
        ("Title", 0), ("Category", 0), ("Price", 1), ("Rating", 1), ("In stock", 0), ("Stock", 1), ("Reviews", 1)))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f"<style>{_CSS}</style></head><body><main><h1>{esc(title)}</h1>"
            f'<p class="sub">Generated {when}</p><div class="tiles">{tiles}</div>'
            f'<div class="panels">{panels}</div>'
            f'<input id="q" type="search" placeholder="Search books..." aria-label="Search books">'
            f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
            f"</main><script>{_JS}</script></body></html>")
