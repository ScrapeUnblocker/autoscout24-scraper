"""Write results as JSON, JSON Lines, CSV or a terminal table."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from typing import Any, TextIO

FORMATS = ("json", "jsonl", "csv", "table")


def as_dict(item: Any) -> dict[str, Any]:
    return item.to_dict() if hasattr(item, "to_dict") else dict(item)


def _cell(value: Any) -> Any:
    """A CSV-friendly value: lists joined with `` | ``, dicts as JSON."""
    if isinstance(value, (list, tuple)):
        if all(not isinstance(v, (dict, list)) for v in value):
            return " | ".join(str(v) for v in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def to_json(items: Sequence[Any] | Any) -> str:
    data = [as_dict(i) for i in items] if isinstance(items, (list, tuple)) else as_dict(items)
    return json.dumps(data, ensure_ascii=False, indent=2)


def to_jsonl(items: Iterable[Any]) -> str:
    return "".join(json.dumps(as_dict(i), ensure_ascii=False) + "\n" for i in items)


def to_csv(items: Iterable[Any]) -> str:
    rows = [as_dict(i) for i in items]
    if not rows:
        return ""
    columns: list[str] = []
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(row.get(k)) for k in columns})
    return buffer.getvalue()


def _money(value: Any, currency: Any) -> str:
    if value is None:
        return "-"
    symbol = "€" if currency == "EUR" else (currency or "")
    return f"{symbol}{value:,}"


def to_table(items: Iterable[Any]) -> str:
    """A compact, human-readable table of listings."""
    header = ("PRICE", "RATING", "REG", "KM", "FUEL", "KW", "CAR", "WHERE")
    rows = [header]
    for item in items:
        d = as_dict(item)
        car = " ".join(str(d[k]) for k in ("make", "model", "version") if d.get(k))
        where = " ".join(str(d[k]) for k in ("country", "city") if d.get(k))
        rows.append(
            (
                _money(d.get("price"), d.get("currency")),
                d.get("price_rating") or "-",
                d.get("first_registration") or "-",
                f"{d['mileage_km']:,}" if d.get("mileage_km") is not None else "-",
                d.get("fuel_type") or d.get("fuel") or "-",
                str(d.get("power_kw") or "-"),
                car[:44] + ("*" if d.get("sponsored") else ""),
                where[:28],
            )
        )
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(header))]
    lines = ["  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]
    return "\n".join(lines) + "\n"


def render(items: Sequence[Any] | Any, fmt: str = "json") -> str:
    if fmt == "json":
        return to_json(items) + "\n"
    many = items if isinstance(items, (list, tuple)) else [items]
    if fmt == "jsonl":
        return to_jsonl(many)
    if fmt == "csv":
        return to_csv(many)
    if fmt == "table":
        return to_table(many)
    raise ValueError(f"unknown format {fmt!r}; choose from: {', '.join(FORMATS)}")


def write(
    items: Sequence[Any] | Any,
    fmt: str = "json",
    path: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Render ``items`` and write them to ``path`` (UTF-8) or ``stream``."""
    text = render(items, fmt)
    if path:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return
    if stream is None:
        import sys

        stream = sys.stdout
    stream.write(text)
