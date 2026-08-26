"""Rectangular-voltage equations for the ACR (rectangular AC) formulation."""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo


def add_acr_voltage_variables(
    model: Any,
    *,
    bus_ids: list[int],
    vm_seed: dict[int, float],
    va_seed: dict[int, float],
    voltage_bounds: dict[int, tuple[float, float]],
) -> None:
    """Add ACR voltage variables and the magnitude-link equations."""
    model.vr = pyo.Var(
        model.BUS,
        initialize={bus: vm_seed[bus] for bus in bus_ids},
        bounds=lambda _m, bus: (-voltage_bounds[bus][1], voltage_bounds[bus][1]),
        within=pyo.Reals,
    )
    model.vi = pyo.Var(
        model.BUS,
        initialize={bus: 0.0 for bus in bus_ids},
        bounds=lambda _m, bus: (-voltage_bounds[bus][1], voltage_bounds[bus][1]),
        within=pyo.Reals,
    )
    model.acr_voltage_magnitude = pyo.Constraint(
        model.BUS,
        rule=lambda m, bus: m.vr[bus] ** 2 + m.vi[bus] ** 2 == m.vm[bus] ** 2,
    )
    model.acr_voltage_angle = pyo.Constraint(
        model.BUS,
        rule=lambda m, bus: m.vr[bus] * pyo.sin(m.va[bus])
        - m.vi[bus] * pyo.cos(m.va[bus])
        == 0.0,
    )


def p_injection(
    model: Any,
    bus: int,
    injections: dict[int, list[tuple[int, int, bool]]],
    branch_g: dict[int, float],
    branch_b: dict[int, float],
    branch_tap: dict[int, float],
    branch_cos_shift: dict[int, float],
    branch_sin_shift: dict[int, float],
) -> Any:
    """Return rectangular real-power injection at one bus."""
    expression = 0.0
    for other, branch_index, from_side in injections.get(bus, []):
        tap = branch_tap[branch_index]
        conductance = branch_g[branch_index]
        susceptance = branch_b[branch_index]
        cos_shift = branch_cos_shift[branch_index]
        sin_shift = branch_sin_shift[branch_index]
        if from_side:
            self_g = conductance / (tap * tap)
            mutual_g = (-conductance * cos_shift + susceptance * sin_shift) / tap
            mutual_b = (-conductance * sin_shift - susceptance * cos_shift) / tap
        else:
            self_g = conductance
            mutual_g = (-conductance * cos_shift - susceptance * sin_shift) / tap
            mutual_b = (conductance * sin_shift - susceptance * cos_shift) / tap
        dot = model.vr[bus] * model.vr[other] + model.vi[bus] * model.vi[other]
        cross = model.vi[bus] * model.vr[other] - model.vr[bus] * model.vi[other]
        expression += self_g * model.vm[bus] ** 2 + mutual_g * dot + mutual_b * cross
    return expression


def q_injection(
    model: Any,
    bus: int,
    injections: dict[int, list[tuple[int, int, bool]]],
    branch_g: dict[int, float],
    branch_b: dict[int, float],
    branch_b_self: dict[int, float],
    branch_tap: dict[int, float],
    branch_cos_shift: dict[int, float],
    branch_sin_shift: dict[int, float],
) -> Any:
    """Return rectangular reactive-power injection at one bus."""
    expression = -model.b_shunt[bus] * model.vm[bus] ** 2
    for other, branch_index, from_side in injections.get(bus, []):
        tap = branch_tap[branch_index]
        conductance = branch_g[branch_index]
        susceptance = branch_b[branch_index]
        self_b = branch_b_self[branch_index]
        cos_shift = branch_cos_shift[branch_index]
        sin_shift = branch_sin_shift[branch_index]
        if from_side:
            self_b /= tap * tap
            mutual_g = (-conductance * cos_shift + susceptance * sin_shift) / tap
            mutual_b = (-conductance * sin_shift - susceptance * cos_shift) / tap
        else:
            mutual_g = (-conductance * cos_shift - susceptance * sin_shift) / tap
            mutual_b = (conductance * sin_shift - susceptance * cos_shift) / tap
        dot = model.vr[bus] * model.vr[other] + model.vi[bus] * model.vi[other]
        cross = model.vi[bus] * model.vr[other] - model.vr[bus] * model.vi[other]
        expression += -self_b * model.vm[bus] ** 2 + mutual_g * cross - mutual_b * dot
    return expression


def branch_power(
    model: Any,
    index: int,
    *,
    from_side: bool,
    branch_g: dict[int, float],
    branch_b: dict[int, float],
    branch_b_self: dict[int, float],
    branch_tap: dict[int, float],
    branch_cos_shift: dict[int, float],
    branch_sin_shift: dict[int, float],
) -> tuple[Any, Any]:
    """Return rectangular P/Q flow for one branch endpoint."""
    branch = model._case.branches[index]
    if from_side:
        local, remote = branch.from_bus, branch.to_bus
        tap = branch_tap[index]
        self_g = branch_g[index] / (tap * tap)
        self_b = branch_b_self[index] / (tap * tap)
        mutual_g = (
            -branch_g[index] * branch_cos_shift[index]
            + branch_b[index] * branch_sin_shift[index]
        ) / tap
        mutual_b = (
            -branch_g[index] * branch_sin_shift[index]
            - branch_b[index] * branch_cos_shift[index]
        ) / tap
    else:
        local, remote = branch.to_bus, branch.from_bus
        self_g = branch_g[index]
        self_b = branch_b_self[index]
        mutual_g = (
            -branch_g[index] * branch_cos_shift[index]
            - branch_b[index] * branch_sin_shift[index]
        ) / branch_tap[index]
        mutual_b = (
            branch_g[index] * branch_sin_shift[index]
            - branch_b[index] * branch_cos_shift[index]
        ) / branch_tap[index]
    dot = model.vr[local] * model.vr[remote] + model.vi[local] * model.vi[remote]
    cross = model.vi[local] * model.vr[remote] - model.vr[local] * model.vi[remote]
    p_flow = self_g * model.vm[local] ** 2 + mutual_g * dot + mutual_b * cross
    q_flow = -self_b * model.vm[local] ** 2 + mutual_g * cross - mutual_b * dot
    return p_flow, q_flow
