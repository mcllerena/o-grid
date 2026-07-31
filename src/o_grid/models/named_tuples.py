"""Named tuple-like helper dataclasses for model fields."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MinMax:
    """Simple minimum/maximum pair for limits."""

    min: float
    max: float


@dataclass(slots=True)
class FromToToFrom:
    """Directional pair values for from->to and to->from quantities."""

    from_to: float
    to_from: float