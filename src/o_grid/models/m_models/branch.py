"""MATPOWER ``branch`` table to o-grid AC branch components."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from o_grid.models.base import AnaredeComponent
from o_grid.models.branch import (
    ACLine,
    PhaseShiftingTransformer,
    SwitchDevice,
    TransformerDevice,
)
from o_grid.models.enums import CircuitState
from o_grid.units import ApparentPower, Percentage, PerUnit

SWITCH_IMPEDANCE_TOLERANCE = 1e-6


def Branch(
    branch: Sequence[Mapping[str, Any]],
    *,
    base_mva: float = 100.0,
) -> list[AnaredeComponent]:
    """Build AC branch components from MATPOWER branch rows."""
    components: list[AnaredeComponent] = []
    circuits: dict[tuple[int, int], int] = {}
    for row in branch:
        from_bus = _int(row.get("F_BUS"))
        to_bus = _int(row.get("T_BUS"))
        pair = (min(from_bus, to_bus), max(from_bus, to_bus))
        circuit = circuits.get(pair, 0) + 1
        circuits[pair] = circuit
        components.append(_build_branch(row, from_bus, to_bus, circuit, base_mva))
    return components


def _build_branch(
    row: Mapping[str, Any],
    from_bus: int,
    to_bus: int,
    circuit: int,
    base_mva: float,
) -> AnaredeComponent:
    resistance = _number(row.get("BR_R", 0.0))
    reactance = _number(row.get("BR_X", 0.0))
    susceptance = _number(row.get("BR_B", 0.0)) * base_mva
    rate_a = _number(row.get("RATE_A", 0.0))
    tap = _number(row.get("TAP", 0.0))
    shift = _number(row.get("SHIFT", 0.0))
    status = _number(row.get("BR_STATUS", 1))
    available = status != 0
    in_service = CircuitState.CLOSED if available else CircuitState.OPEN

    is_phase_shifter = shift != 0.0
    is_transformer = not is_phase_shifter and tap != 0.0
    is_switch = (
        not is_phase_shifter
        and not is_transformer
        and max(abs(resistance), abs(reactance)) <= SWITCH_IMPEDANCE_TOLERANCE
    )

    if is_phase_shifter:
        model: Callable[..., AnaredeComponent] = PhaseShiftingTransformer
    elif is_transformer:
        model = TransformerDevice
    elif is_switch:
        model = SwitchDevice
    else:
        model = ACLine

    common: dict[str, Any] = {
        "name": f"{from_bus}_{to_bus}_{circuit}",
        "from_bus": from_bus,
        "to_bus": to_bus,
        "line_circuit": circuit,
        "available": available,
        "from_bus_opening": in_service,
        "to_bus_opening": in_service,
        "normal_capacity": ApparentPower(rate_a, "MVA"),
        "r": Percentage(resistance * 100.0, "%"),
        "x": Percentage(reactance * 100.0, "%"),
    }
    if is_phase_shifter or is_transformer:
        common["tap"] = PerUnit(tap if tap != 0.0 else 1.0, "pu")

    component = model(**common)
    component.ext["pwf_values"] = {
        "from_bus": from_bus,
        "to_bus": to_bus,
        "resistance": resistance * 100.0,
        "reactance": reactance * 100.0,
        "susceptance": susceptance,
        "tap": tap if tap != 0.0 else 1.0,
        "phase_shift": -shift,
        "normal_capacity": rate_a,
        "tap_minimum": 0.0,
        "tap_maximum": 0.0,
    }
    return component


def branch_block(component: AnaredeComponent) -> str:
    """Return the o-grid block key that owns an AC branch component."""
    if isinstance(component, ACLine):
        return "DLIN"
    if isinstance(component, PhaseShiftingTransformer):
        return "DLIN_PHASE_SHIFT"
    if isinstance(component, TransformerDevice):
        return "DLIN_TRANSFORMER"
    return "DLIN_SWITCH"


def _int(value: Any) -> int:
    return int(float(value))


def _number(value: Any) -> float:
    return float(value)
