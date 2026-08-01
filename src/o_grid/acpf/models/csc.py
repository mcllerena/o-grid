"""Controllable series compensator static network application."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from o_grid.models import ControllableSeriesCompensator
from o_grid.units import get_magnitude

if TYPE_CHECKING:
    from o_grid.acpf.models.case import BranchData


def apply_csc_to_branches(
    components: Iterable[ControllableSeriesCompensator],
    branches: list[BranchData],
    branch_factory: Callable[..., BranchData],
) -> None:
    """Add active CSC reactance to a matching branch or stamp a standalone branch."""
    by_circuit = {
        (branch.from_bus, branch.to_bus, branch.circuit): branch for branch in branches
    }
    for component in components:
        if not is_active_csc(component):
            continue
        values = _values(component)
        from_bus = _bus_number(getattr(component, "from_bus", values.get("from_bus")))
        to_bus = _bus_number(getattr(component, "to_bus", values.get("to_bus")))
        circuit = _integer(getattr(component, "dcsc_circuit", None), 1)
        reactance = _magnitude(
            getattr(component, "initial_reactance", None), values.get("initial_reactance", 0.0)
        ) * 0.01
        branch = by_circuit.get((from_bus, to_bus, circuit))
        if branch is None:
            branch = by_circuit.get((to_bus, from_bus, circuit))
        if branch is not None:
            branch.reactance += reactance
            continue
        standalone = branch_factory(
            from_bus=from_bus,
            to_bus=to_bus,
            circuit=circuit,
            resistance=0.0,
            reactance=reactance,
            charging=0.0,
            tap=1.0,
            phase_shift=0.0,
            rating=_magnitude(
                getattr(component, "dcsc_capacity", None), values.get("dcsc_capacity", 0.0)
            ),
        )
        branches.append(standalone)
        by_circuit[(from_bus, to_bus, circuit)] = standalone


def is_active_csc(component: ControllableSeriesCompensator) -> bool:
    """Return whether a CSC participates in the C++ static network model."""
    values = _values(component)
    return (
        bool(getattr(component, "available", True))
        and str(values.get("operation") or "A").upper() != "E"
        and str(values.get("state") or "L").upper() != "D"
        and str(getattr(component, "bypass", values.get("bypass", "D"))).upper() != "L"
    )


def _values(component: object) -> dict[str, Any]:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}


def _magnitude(value: object, default: float = 0.0) -> float:
    return float(get_magnitude(value)) if value is not None else float(default)


def _bus_number(value: object) -> int:
    return int(float(str(getattr(value, "number", value))))


def _integer(value: object, default: int) -> int:
    try:
        return int(float(str(value))) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
