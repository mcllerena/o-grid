"""Lifted voltage equations for the ACT (angle-cross-product) formulation."""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo


def add_act_voltage_variables(
    model: Any,
    *,
    bus_ids: list[int],
    vm_seed: dict[int, float],
    va_seed: dict[int, float],
    voltage_bounds: dict[int, tuple[float, float]],
    buspairs: list[tuple[int, int]],
) -> None:
    """Add ACT voltage-square, angle, and cross-product variables."""
    model.w = pyo.Var(
        model.BUS,
        initialize={bus: vm_seed[bus] ** 2 for bus in bus_ids},
        bounds=lambda _m, bus: (voltage_bounds[bus][0] ** 2, voltage_bounds[bus][1] ** 2),
        within=pyo.NonNegativeReals,
    )
    model.wr = pyo.Var(
        pyo.Set(initialize=buspairs, dimen=2),
        initialize={(i, j): vm_seed[i] * vm_seed[j] for i, j in buspairs},
        within=pyo.Reals,
    )
    model.wi = pyo.Var(
        pyo.Set(initialize=buspairs, dimen=2),
        initialize={(i, j): 0.0 for i, j in buspairs},
        within=pyo.Reals,
    )
    model.act_voltage_square = pyo.Constraint(
        model.BUS,
        rule=lambda m, bus: m.w[bus] == m.vm[bus] ** 2,
    )
    model.act_voltage_product = pyo.Constraint(
        model.wr.index_set(),
        rule=lambda m, i, j: m.wr[i, j] ** 2 + m.wi[i, j] ** 2 == m.w[i] * m.w[j],
    )
    model.act_tangent_relation = pyo.Constraint(
        model.wr.index_set(),
        rule=lambda m, i, j: m.wi[i, j] == pyo.tan(m.va[i] - m.va[j]) * m.wr[i, j],
    )


def _pair(model: Any, bus: int, other: int) -> tuple[Any, Any]:
    """Return the oriented ACT cross products for a bus pair."""
    if (bus, other) in model.wr:
        return model.wr[bus, other], model.wi[bus, other]
    return model.wr[other, bus], -model.wi[other, bus]


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
    """Return ACT lifted real-power injection."""
    expression = 0.0
    for other, branch_index, from_side in injections.get(bus, []):
        tap = branch_tap[branch_index]
        conductance = branch_g[branch_index]
        susceptance = branch_b[branch_index]
        cos_shift = branch_cos_shift[branch_index]
        sin_shift = branch_sin_shift[branch_index]
        if from_side:
            self_g = conductance / tap**2
            mutual_g = (-conductance * cos_shift + susceptance * sin_shift) / tap
            mutual_b = (-conductance * sin_shift - susceptance * cos_shift) / tap
        else:
            self_g = conductance
            mutual_g = (-conductance * cos_shift - susceptance * sin_shift) / tap
            mutual_b = (conductance * sin_shift - susceptance * cos_shift) / tap
        wr, wi = _pair(model, bus, other)
        expression += self_g * model.w[bus] + mutual_g * wr + mutual_b * wi
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
    """Return ACT lifted reactive-power injection."""
    expression = -model.b_shunt[bus] * model.w[bus]
    for other, branch_index, from_side in injections.get(bus, []):
        tap = branch_tap[branch_index]
        conductance = branch_g[branch_index]
        susceptance = branch_b[branch_index]
        self_b = (
            branch_b_self[branch_index] / tap**2
            if from_side
            else branch_b_self[branch_index]
        )
        if from_side:
            mutual_g = (
                -conductance * branch_cos_shift[branch_index]
                + susceptance * branch_sin_shift[branch_index]
            ) / tap
            mutual_b = (
                -conductance * branch_sin_shift[branch_index]
                - susceptance * branch_cos_shift[branch_index]
            ) / tap
        else:
            mutual_g = (
                -conductance * branch_cos_shift[branch_index]
                - susceptance * branch_sin_shift[branch_index]
            ) / tap
            mutual_b = (
                conductance * branch_sin_shift[branch_index]
                - susceptance * branch_cos_shift[branch_index]
            ) / tap
        wr, wi = _pair(model, bus, other)
        expression += -self_b * model.w[bus] + mutual_g * wi - mutual_b * wr
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
    """Return ACT lifted real/reactive branch flow."""
    branch = model._case.branches[index]
    local = branch.from_bus if from_side else branch.to_bus
    remote = branch.to_bus if from_side else branch.from_bus
    tap = branch_tap[index]
    if from_side:
        self_g = branch_g[index] / tap**2
        self_b = branch_b_self[index] / tap**2
        mutual_g = (
            -branch_g[index] * branch_cos_shift[index]
            + branch_b[index] * branch_sin_shift[index]
        ) / tap
        mutual_b = (
            -branch_g[index] * branch_sin_shift[index]
            - branch_b[index] * branch_cos_shift[index]
        ) / tap
    else:
        self_g = branch_g[index]
        self_b = branch_b_self[index]
        mutual_g = (
            -branch_g[index] * branch_cos_shift[index]
            - branch_b[index] * branch_sin_shift[index]
        ) / tap
        mutual_b = (
            branch_g[index] * branch_sin_shift[index]
            - branch_b[index] * branch_cos_shift[index]
        ) / tap
    wr, wi = _pair(model, local, remote)
    return (
        self_g * model.w[local] + mutual_g * wr + mutual_b * wi,
        -self_b * model.w[local] + mutual_g * wi - mutual_b * wr,
    )
