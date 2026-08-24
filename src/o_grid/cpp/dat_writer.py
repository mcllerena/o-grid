"""Writer for the native C++ power-flow ``param:`` data format."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def write_dat(path: str | Path, source: str | Path, sections: Mapping[str, Iterable[Mapping[str, Any]]], config: Mapping[str, Any]) -> Path:
    destination = Path(path)
    lines = [f"# Generated from {source}", ""]
    field_order = config.get("field_order", {})
    aliases = config.get("name_aliases", {})
    for section, records in sections.items():
        rows = list(records)
        if not rows:
            continue
        available = list(rows[0])
        preferred = [name for name in field_order.get(section, []) if name in available]
        fields = preferred + [name for name in available if name not in preferred]
        headers = [aliases.get(name, name[:12]) for name in fields]
        values = [[format_dat_value(record.get(name)) for name in fields] for record in rows]
        widths = [len(header) for header in headers]
        for row in values:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(value))
        left = {index for row in values for index, value in enumerate(row) if value.startswith('"')}
        prefix = f"param: {section}: "
        lines.append(prefix + "  ".join(
            value.ljust(widths[index]) if index in left else value.rjust(widths[index])
            for index, value in enumerate(headers)
        ) + " :=")
        row_prefix = " " * len(prefix)
        for row in values:
            lines.append(row_prefix + "  ".join(
                value.ljust(widths[index]) if index in left else value.rjust(widths[index])
                for index, value in enumerate(row)
            ))
        lines.extend([";", ""])
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return destination


def format_dat_value(value: Any) -> str:
    if value is None or value == "" or value == ".":
        return "0"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)
