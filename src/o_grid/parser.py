"""Parsing entry points for o-grid datasets."""

from __future__ import annotations

from typing import Any

from o_grid.constants import REQUIRED_KEYS
from o_grid.utils.utils_parser import normalize_row


def parse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse and validate input rows."""
    return [normalize_row(row, REQUIRED_KEYS) for row in rows]
