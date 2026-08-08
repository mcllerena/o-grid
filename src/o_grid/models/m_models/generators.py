"""MATPOWER ``gen`` table to o-grid generator components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from o_grid.models.generators import Generator
from o_grid.units import ActivePower


def Generators(gen: Sequence[Mapping[str, Any]]) -> list[Generator]:
    """Build ``Generator`` components from MATPOWER gen rows."""
    components: list[Generator] = []
    for record_index, row in enumerate(gen, start=1):
        bus_number = _int(row.get("GEN_BUS"))
        components.append(
            Generator(
                name=f"generator-{bus_number}-{record_index}",
                number=bus_number,
                active_generation=ActivePower(_number(row.get("PG", 0.0)), "MW"),
                min_active_generation=ActivePower(_number(row.get("PMIN", 0.0)), "MW"),
                max_active_generation=ActivePower(_number(row.get("PMAX", 0.0)), "MW"),
            )
        )
    return components


def _int(value: Any) -> int:
    return int(float(value))


def _number(value: Any) -> float:
    return float(value)
