"""Named tuple-like helper dataclasses for model fields."""

from __future__ import annotations

from dataclasses import dataclass

from o_grid.units import ActivePower, ReactivePower


@dataclass(slots=True)
class MinMax:
    """Simple minimum/maximum pair for limits."""

    min: float
    max: float


@dataclass(slots=True)
class FromToToFrom:
    """Directional pair values for from->to and to->from quantities."""

    from_to: float | ActivePower | ReactivePower
    to_from: float | ActivePower | ReactivePower
