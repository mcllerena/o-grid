"""Base classes for o_grid models."""

from __future__ import annotations

from typing import ClassVar, TypeAlias

from infrasys import Component

ParsedScalar: TypeAlias = int | float | str | None


class AnaredeComponent(Component):
    """Base infrasys component for ANAREDE-derived models."""

    name: str = ""
    record_index: int = 0
    raw_line: str = ""
    block: ClassVar[str] = ""
