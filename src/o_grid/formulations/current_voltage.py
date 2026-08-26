"""Current-voltage equations for the IVR (current-voltage rectangular) formulation."""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo


def add_ivr_variables(
    model: Any,
    *,
    voltage_bounds: dict[int, tuple[float, float]],
    vm_seed: dict[int, float],
) -> None:
    """Add rectangular voltage and directed branch-current variables."""
    model.vr = pyo.Var(
        model.BUS,
        initialize=vm_seed,
        bounds=lambda _m, bus: (-voltage_bounds[bus][1], voltage_bounds[bus][1]),
    )
    model.vi = pyo.Var(
        model.BUS,
        initialize=0.0,
        bounds=lambda _m, bus: (-voltage_bounds[bus][1], voltage_bounds[bus][1]),
    )
    model.cr_from = pyo.Var(model.BRANCH, initialize=0.0, within=pyo.Reals)
    model.ci_from = pyo.Var(model.BRANCH, initialize=0.0, within=pyo.Reals)
    model.cr_to = pyo.Var(model.BRANCH, initialize=0.0, within=pyo.Reals)
    model.ci_to = pyo.Var(model.BRANCH, initialize=0.0, within=pyo.Reals)
    model.ivr_voltage_magnitude = pyo.Constraint(
        model.BUS,
        rule=lambda m, bus: m.vr[bus] ** 2 + m.vi[bus] ** 2 == m.vm[bus] ** 2,
    )
    model.ivr_voltage_angle = pyo.Constraint(
        model.BUS,
        rule=lambda m, bus: m.vr[bus] * pyo.sin(m.va[bus])
        - m.vi[bus] * pyo.cos(m.va[bus]) == 0.0,
    )


def add_ivr_branch_equations(
    model: Any,
    *,
    branches: list[Any],
    branch_yff_g: dict[int, float],
    branch_yff_b: dict[int, float],
    branch_yft_g: dict[int, float],
    branch_yft_b: dict[int, float],
    branch_ytf_g: dict[int, float],
    branch_ytf_b: dict[int, float],
    branch_ytt_g: dict[int, float],
    branch_ytt_b: dict[int, float],
) -> None:
    """Add rectangular Ohm equations and power/current expressions."""
    def from_current_real(m: Any, index: int):
        branch = branches[index]
        return m.cr_from[index] == (
            branch_yff_g[index] * m.vr[branch.from_bus]
            - branch_yff_b[index] * m.vi[branch.from_bus]
            + branch_yft_g[index] * m.vr[branch.to_bus]
            - branch_yft_b[index] * m.vi[branch.to_bus]
        )

    def from_current_imag(m: Any, index: int):
        branch = branches[index]
        return m.ci_from[index] == (
            branch_yff_b[index] * m.vr[branch.from_bus]
            + branch_yff_g[index] * m.vi[branch.from_bus]
            + branch_yft_b[index] * m.vr[branch.to_bus]
            + branch_yft_g[index] * m.vi[branch.to_bus]
        )

    def to_current_real(m: Any, index: int):
        branch = branches[index]
        return m.cr_to[index] == (
            branch_ytf_g[index] * m.vr[branch.from_bus]
            - branch_ytf_b[index] * m.vi[branch.from_bus]
            + branch_ytt_g[index] * m.vr[branch.to_bus]
            - branch_ytt_b[index] * m.vi[branch.to_bus]
        )

    def to_current_imag(m: Any, index: int):
        branch = branches[index]
        return m.ci_to[index] == (
            branch_ytf_b[index] * m.vr[branch.from_bus]
            + branch_ytf_g[index] * m.vi[branch.from_bus]
            + branch_ytt_b[index] * m.vr[branch.to_bus]
            + branch_ytt_g[index] * m.vi[branch.to_bus]
        )

    model.ivr_current_from_real = pyo.Constraint(model.BRANCH, rule=from_current_real)
    model.ivr_current_from_imag = pyo.Constraint(model.BRANCH, rule=from_current_imag)
    model.ivr_current_to_real = pyo.Constraint(model.BRANCH, rule=to_current_real)
    model.ivr_current_to_imag = pyo.Constraint(model.BRANCH, rule=to_current_imag)


def branch_power(model: Any, index: int, *, from_side: bool) -> tuple[Any, Any]:
    """Return P/Q as the rectangular product of voltage and current."""
    branch = model._case.branches[index]
    bus = branch.from_bus if from_side else branch.to_bus
    real = model.cr_from[index] if from_side else model.cr_to[index]
    imag = model.ci_from[index] if from_side else model.ci_to[index]
    return (
        model.vr[bus] * real + model.vi[bus] * imag,
        model.vi[bus] * real - model.vr[bus] * imag,
    )
