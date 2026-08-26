"""Linear active-power formulations from the DCP.jl library."""

from __future__ import annotations

from typing import Any


def p_injection(
    model: Any,
    bus: int,
    injections: dict[int, list[tuple[int, int, bool]]],
    branch_b: dict[int, float],
) -> Any:
    """Return the DCP nodal active-power injection."""
    expression = 0.0
    for other, branch_index, _from_side in injections.get(bus, []):
        expression += -branch_b[branch_index] * (model.va[bus] - model.va[other])
    return expression


def branch_power(
    model: Any,
    index: int,
    *,
    from_side: bool,
    branch_b: dict[int, float],
    branch_x: dict[int, float],
    branch_tap: dict[int, float],
    branch_phase_shift: dict[int, float],
    transformer_aware: bool,
) -> Any:
    """Return a DCP active branch flow, optionally including transformer data."""
    branch = model._case.branches[index]
    delta = model.va[branch.from_bus] - model.va[branch.to_bus]
    if transformer_aware:
        x = branch_x[index]
        flow = (delta - branch_phase_shift[index]) / (x * branch_tap[index])
    else:
        flow = -branch_b[index] * delta
    return flow if from_side else -flow
