"""Exporter utility helpers."""

from __future__ import annotations


def format_row(row: dict[str, object], separator: str = ",") -> str:
    """Format a dictionary row as a stable delimited line."""
    ordered_keys = sorted(row)
    values = [str(row[key]) for key in ordered_keys]
    return separator.join(values)


def format_rows(rows: list[dict[str, object]], separator: str = ",") -> str:
    """Format multiple rows into newline-separated text."""
    return "\n".join(format_row(row, separator=separator) for row in rows)
