"""Export entry points for o-grid datasets."""

from __future__ import annotations

from o_grid.constants import DEFAULT_SEPARATOR
from o_grid.utils.utils_exporter import format_rows


def export_rows(rows: list[dict[str, object]], separator: str = DEFAULT_SEPARATOR) -> str:
    """Serialize rows into delimited text."""
    return format_rows(rows, separator=separator)
