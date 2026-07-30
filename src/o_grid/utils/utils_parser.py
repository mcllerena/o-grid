"""Parser utility helpers."""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float:
    """Convert a supported value to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return float(stripped)
    raise TypeError(f"unsupported value type: {type(value)!r}")


def normalize_row(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Validate and normalize a row used by parsers."""
    missing = [key for key in keys if key not in row]
    if missing:
        raise KeyError(f"missing keys: {', '.join(missing)}")

    normalized = dict(row)
    normalized["load_mw"] = to_float(normalized["load_mw"])
    normalized["generator_mw"] = to_float(normalized["generator_mw"])
    return normalized
