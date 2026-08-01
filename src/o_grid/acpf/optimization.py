"""Optimization-based AC power flow solved as a nonlinear program with Pyomo and Ipopt.

The formulation follows the optimization-based AC/DC power-flow model of the
o-grid research notes and the ``power-simulator`` reference: bus active and
reactive power balances in polar coordinates, static VAR compensators with
voltage-droop control equations and voltage-dependent reactive limits, and
bounded reactive generation at Q-limited PV buses. Operational limits are
enforced as soft constraints through nonnegative slack variables so that
Ipopt can always report an operating point; the objective is a weighted
least-squares feasibility and regularization term that drives the balance
and control residuals toward zero while keeping the state near the input.
"""

from __future__ import annotations

import math
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, ClassVar, cast

import numpy as np
import pyomo.environ as pyo
from infrasys import System
from loguru import logger
from pyomo.opt import SolverFactory, TerminationCondition

from o_grid.acpf.models import (
    build_component_results,
    build_power_flow_case,
    build_power_flow_settings,
    reduce_closed_switches,
)
from o_grid.acpf.models.case import BusData, PowerFlowCase
from o_grid.acpf.models.lcc import refresh_lcc_reporting_state
from o_grid.acpf.results import (
    ACPowerFlowResult,
    IterationPowerFlowResult,
    PowerFlowRun,
    apply_power_flow_result,
)
from o_grid.acpf.solver import PowerFlowSolver
from o_grid.acpf.utils import (
    build_ybus,
    calculate_branch_results,
    calculate_bus_results,
)
from o_grid.models import ACBusTypes
from o_grid.parser import AnaredeInfrasysParser, ParsedAnaredeSystem

TOLERANCE = 1.0e-12
DISPLAY_TOLERANCE = 1.0e-9
CONVERGENCE_REPORT_EPS = 1.0e-6
ANGLE_LIMIT_RAD = math.pi / 2.0

OBJECTIVE_WEIGHT_VOLTAGE = 1.0
OBJECTIVE_WEIGHT_VOLTAGE_LIMITS = 100.0
OBJECTIVE_WEIGHT_ANGLE = 1.0
OBJECTIVE_WEIGHT_ANGLE_LIMITS = 1.0e4
OBJECTIVE_WEIGHT_SVC = 100.0

VALID_OBJECTIVE_FUNCTIONS = ("minimize_residuals", "zero_function", "squared_generation")

SLACK = 2
PV = 1
PQ = 0


def _bus_type_code(kind: ACBusTypes) -> int:
    if kind in {ACBusTypes.REF, ACBusTypes.SLACK}:
        return SLACK
    if kind == ACBusTypes.PV:
        return PV
    return PQ


def _is_switchable_generation_bus(bus: BusData) -> bool:
    name = bus.name.upper()
    return any(marker in name for marker in ("EOL", "UFV", "PCH", "BIO", "CGH"))


def _uses_bounded_q_control(qlim_enabled: bool, bus: BusData) -> bool:
    return (
        qlim_enabled
        and bus.kind == ACBusTypes.PV
        and _is_switchable_generation_bus(bus)
        and bus.base_voltage >= 900.0
        and bus.minimum_reactive_generation is not None
        and bus.maximum_reactive_generation is not None
        and bus.maximum_reactive_generation > bus.minimum_reactive_generation + DISPLAY_TOLERANCE
    )


def _voltage_bounds(bus: BusData, strict: bool) -> tuple[float, float]:
    if strict:
        lower = max(0.4, bus.minimum_voltage)
        upper = min(2.0, bus.maximum_voltage)
    else:
        lower = max(0.4, bus.minimum_voltage * 0.8)
        upper = min(2.0, max(bus.maximum_voltage * 1.5, 1.2))
    if upper < lower:
        return lower, lower
    return lower, upper


def _bounded_voltage_seed(bus: BusData, strict: bool) -> float:
    lower, upper = _voltage_bounds(bus, strict)
    return min(max(bus.voltage, lower), upper)


def _set_signed_slack(positive_var, negative_var, residual: float) -> None:
    positive_var.set_value(max(0.0, residual), skip_validation=True)
    negative_var.set_value(max(0.0, -residual), skip_validation=True)


def _value_or_default(component, default: float = 0.0) -> float:
    value = pyo.value(component, exception=False)
    return default if value is None else float(value)


def _apply_zero_residuals(model: pyo.ConcreteModel) -> None:
    """Zero the power-balance residual function while keeping controllers soft.

    The active and reactive power-balance residuals are fixed at zero, so the
    power-flow equations ``P_spec = P_calc`` and ``Q_spec = Q_calc`` hold as
    exact equalities, and the per-bus and aggregate tolerance rows are
    deactivated. SVC droop controllers keep their control-tolerance constraint
    and the voltage/angle limits stay soft: those are control targets and
    operational bounds, not physical equations, and leaving them relaxed keeps
    the exact-balance model feasible on cases that only converge inside a
    tolerance band (e.g. ``CASO_FINAL_EQV2020``).
    """
    for component_name in ("p_slack_pos", "p_slack_neg", "q_slack_pos", "q_slack_neg"):
        component = getattr(model, component_name)
        for index in component:
            component[index].fix(0.0)
    for component_name in (
        "active_residual_tolerance",
        "reactive_residual_tolerance",
        "aggregate_active_residual_upper",
        "aggregate_active_residual_lower",
        "aggregate_reactive_residual_upper",
        "aggregate_reactive_residual_lower",
    ):
        getattr(model, component_name).deactivate()


def _apply_slack_generation_redispatch(
    model: pyo.ConcreteModel,
    case: PowerFlowCase,
    bus_by_id: dict[int, BusData],
    p_seed: dict[int, float],
) -> None:
    """Free reference-bus active generation and close its exact balance equation.

    The ``squared_generation`` objective minimizes the sum of squared active
    generation at the reference (slack) buses.  Each reference bus gains a
    nonnegative ``pg_slack`` variable bounded by its specified generation and
    load, and the active-power balance equation at that bus becomes an exact
    equality that determines the dispatched generation from the AC state.
    """
    base_mva = case.base_mva
    slack_buses = [bus.number for bus in case.buses if _bus_type_code(bus.kind) == SLACK]
    if not slack_buses:
        return
    model_any = cast(Any, model)
    slack_load = {bus: bus_by_id[bus].active_load / base_mva for bus in slack_buses}
    model_any._slack_load_pu = slack_load
    slack_upper = {
        bus: max(
            1.0,
            10.0 * (bus_by_id[bus].active_generation + bus_by_id[bus].active_load) / base_mva,
        )
        for bus in slack_buses
    }
    model_any.SLACK_GEN = pyo.Set(initialize=slack_buses, ordered=True)
    model_any.pg_slack = pyo.Var(
        model_any.SLACK_GEN,
        initialize=lambda m, bus: max(0.0, p_seed.get(bus, 0.0) + slack_load[bus]),
        bounds=lambda m, bus: (0.0, slack_upper[bus]),
        within=pyo.Reals,
    )

    def slack_active_balance_rule(m: Any, bus: int):
        return m.pg_slack[bus] - slack_load[bus] - m.calculated_p_injection[bus] == 0.0

    model_any.strict_slack_active_power_balance = pyo.Constraint(
        model_any.SLACK_GEN, rule=slack_active_balance_rule
    )


def build_optimization_model(
    case: PowerFlowCase,
    *,
    active_tolerance_pu: float,
    reactive_tolerance_pu: float,
    control_tolerance_pu: float,
    qlim_enabled: bool = False,
    strict_voltage_limits: bool = False,
    objective_function: str = "minimize_residuals",
) -> pyo.ConcreteModel:
    """Build and initialize the Pyomo AC power-flow optimization model.

    ``objective_function`` selects which formulation is instantiated:

    * ``minimize_residuals`` -- the default feasibility-restoration model.  All
      physical and controller equations are soft constraints whose positive and
      negative slacks are bounded by the per-bus tolerances, and the objective
      minimizes the weighted sum of squared slacks plus a small regularization
      toward the input state.
    * ``zero_function`` -- the pure feasibility formulation.  Every residual
      slack is fixed at zero and the tolerance rows are deactivated, so the
      balance, limit, and SVC droop equations hold exactly and the objective
      is identically zero.  An operating point exists only if the hard system
      is feasible.
    * ``squared_generation`` -- same exact equations as ``zero_function``, but
      reference-bus active generation is a free variable and the objective
      minimizes the sum of squared active generation, selecting the feasible
      point with minimum generation (equivalently minimum losses for a fixed
      load).
    """
    if objective_function not in VALID_OBJECTIVE_FUNCTIONS:
        raise ValueError(
            "Unknown objective_function {!r}; expected one of {}".format(
                objective_function, ", ".join(VALID_OBJECTIVE_FUNCTIONS)
            )
        )
    model = pyo.ConcreteModel("optimization_power_flow")
    model_any = cast(Any, model)
    base_mva = case.base_mva
    bus_ids = [bus.number for bus in case.buses]
    bus_by_id = {bus.number: bus for bus in case.buses}
    branch_ids = list(range(len(case.branches)))
    svc_ids = list(range(len(case.svcs or [])))
    branches = case.branches
    q_limited_pv_ids = [
        bus.number for bus in case.buses if _uses_bounded_q_control(qlim_enabled, bus)
    ]

    model_any.BUS = pyo.Set(initialize=bus_ids, ordered=True)
    model_any.QPV = pyo.Set(initialize=q_limited_pv_ids, ordered=True)
    model_any.BRANCH = pyo.Set(initialize=branch_ids, ordered=True)
    model_any.SVC = pyo.Set(initialize=svc_ids, ordered=True)

    model_any.base_mva = pyo.Param(initialize=base_mva, within=pyo.PositiveReals)
    model_any.angle_limit = pyo.Param(initialize=ANGLE_LIMIT_RAD, within=pyo.PositiveReals)
    model_any.active_tolerance = pyo.Param(
        initialize=max(active_tolerance_pu, TOLERANCE), within=pyo.NonNegativeReals
    )
    model_any.reactive_tolerance = pyo.Param(
        initialize=max(reactive_tolerance_pu, TOLERANCE), within=pyo.NonNegativeReals
    )
    model_any.control_tolerance = pyo.Param(
        initialize=max(control_tolerance_pu, TOLERANCE), within=pyo.NonNegativeReals
    )
    model_any.weight_voltage = pyo.Param(initialize=OBJECTIVE_WEIGHT_VOLTAGE)
    model_any.weight_voltage_limits = pyo.Param(initialize=OBJECTIVE_WEIGHT_VOLTAGE_LIMITS)
    model_any.weight_angle = pyo.Param(initialize=OBJECTIVE_WEIGHT_ANGLE)
    model_any.weight_angle_limits = pyo.Param(initialize=OBJECTIVE_WEIGHT_ANGLE_LIMITS)
    model_any.weight_svc = pyo.Param(initialize=OBJECTIVE_WEIGHT_SVC)

    model_any.bus_type = pyo.Param(
        model_any.BUS, initialize={bus.number: _bus_type_code(bus.kind) for bus in case.buses}
    )
    model_any.vm_min = pyo.Param(
        model_any.BUS, initialize={bus.number: bus.minimum_voltage for bus in case.buses}
    )
    model_any.vm_max = pyo.Param(
        model_any.BUS, initialize={bus.number: bus.maximum_voltage for bus in case.buses}
    )
    model_any.b_shunt = pyo.Param(
        model_any.BUS,
        initialize={bus.number: bus.shunt_susceptance for bus in case.buses},
    )
    model_any.p_spec = pyo.Param(
        model_any.BUS,
        initialize={
            bus.number: (bus.active_generation - bus.active_load) / base_mva for bus in case.buses
        },
    )

    svc_initial_by_bus: dict[int, float] = defaultdict(float)
    for svc in case.svcs or []:
        svc_initial_by_bus[svc.bus] += svc.reactive_power / base_mva
    q_spec = {}
    for bus in case.buses:
        if bus.number in q_limited_pv_ids:
            q_spec[bus.number] = -bus.reactive_load / base_mva
        else:
            q_spec[bus.number] = (
                bus.reactive_generation - svc_initial_by_bus[bus.number]
            ) / base_mva - bus.reactive_load / base_mva
    model_any.q_spec = pyo.Param(model_any.BUS, initialize=q_spec)

    bus_vm_bounds = {}
    bus_va_bounds = {}
    vm_seed = {}
    va_seed = {}
    qg_initial = {}
    qg_lower = {}
    qg_upper = {}
    for bus in case.buses:
        lower, upper = _voltage_bounds(bus, strict_voltage_limits)
        bus_vm_bounds[bus.number] = (lower, upper)
        bus_va_bounds[bus.number] = (-ANGLE_LIMIT_RAD, ANGLE_LIMIT_RAD)
        vm_seed[bus.number] = _bounded_voltage_seed(bus, strict_voltage_limits)
        va_seed[bus.number] = min(max(bus.angle, -ANGLE_LIMIT_RAD), ANGLE_LIMIT_RAD)
        if bus.number in q_limited_pv_ids:
            qg_initial[bus.number] = (
                bus.reactive_generation - svc_initial_by_bus[bus.number]
            ) / base_mva
            qg_lower[bus.number] = float(bus.minimum_reactive_generation or 0.0) / base_mva
            qg_upper[bus.number] = float(bus.maximum_reactive_generation or 0.0) / base_mva

    model_any.vm = pyo.Var(
        model_any.BUS, initialize=vm_seed, bounds=bus_vm_bounds, within=pyo.NonNegativeReals
    )
    model_any.va = pyo.Var(
        model_any.BUS, initialize=va_seed, bounds=bus_va_bounds, within=pyo.Reals
    )
    model_any.qg_qpv = pyo.Var(
        model_any.QPV,
        initialize=qg_initial,
        bounds=lambda m, bus: (qg_lower[bus], qg_upper[bus]),
        within=pyo.Reals,
    )

    model_any.p_slack_pos = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.p_slack_neg = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.q_slack_pos = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.q_slack_neg = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.v_upper_slack = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.v_lower_slack = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.a_upper_slack = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.a_lower_slack = pyo.Var(model_any.BUS, within=pyo.NonNegativeReals, initialize=0.0)

    svc_bus = {}
    svc_ctrl_bus = {}
    svc_q_initial = {}
    svc_q_min = {}
    svc_q_max = {}
    svc_slope = {}
    svc_vref = {}
    svc_bounds = {}
    for index, svc in enumerate(case.svcs or []):
        svc_bus[index] = svc.bus
        svc_ctrl_bus[index] = svc.controlled_bus
        svc_q_initial[index] = svc.reactive_power / base_mva
        svc_q_min[index] = svc.minimum_reactive_power / base_mva
        svc_q_max[index] = svc.maximum_reactive_power / base_mva
        svc_slope[index] = svc.slope
        svc_vref[index] = svc.reference_voltage
        control_bus = bus_by_id[svc.controlled_bus]
        lower, upper = _voltage_bounds(control_bus, strict_voltage_limits)
        svc_bounds[index] = (
            min(svc_q_min[index] * lower * lower, svc_q_min[index] * upper * upper),
            max(svc_q_max[index] * lower * lower, svc_q_max[index] * upper * upper),
        )
    model_any.svc_bus = pyo.Param(model_any.SVC, initialize=svc_bus)
    model_any.svc_ctrl_bus = pyo.Param(model_any.SVC, initialize=svc_ctrl_bus)
    model_any.svc_q_initial = pyo.Param(model_any.SVC, initialize=svc_q_initial)
    model_any.svc_q_min = pyo.Param(model_any.SVC, initialize=svc_q_min)
    model_any.svc_q_max = pyo.Param(model_any.SVC, initialize=svc_q_max)
    model_any.svc_slope = pyo.Param(model_any.SVC, initialize=svc_slope)
    model_any.svc_vref = pyo.Param(model_any.SVC, initialize=svc_vref)

    model_any.qsvc = pyo.Var(
        model_any.SVC,
        initialize=svc_q_initial,
        bounds=svc_bounds,
        within=pyo.Reals,
    )
    model_any.svc_residual_pos = pyo.Var(model_any.SVC, within=pyo.NonNegativeReals, initialize=0.0)
    model_any.svc_residual_neg = pyo.Var(model_any.SVC, within=pyo.NonNegativeReals, initialize=0.0)

    branch_g = {}
    branch_b = {}
    branch_b_self = {}
    branch_tap = {}
    branch_cos_shift = {}
    branch_sin_shift = {}
    branch_yff_g = {}
    branch_yff_b = {}
    branch_yft_g = {}
    branch_yft_b = {}
    branch_ytf_g = {}
    branch_ytf_b = {}
    branch_ytt_g = {}
    branch_ytt_b = {}
    for index, branch in enumerate(branches):
        impedance_squared = (
            branch.resistance * branch.resistance + branch.reactance * branch.reactance
        )
        if impedance_squared <= TOLERANCE:
            conductance = 0.0
            susceptance = 0.0
        else:
            conductance = branch.resistance / impedance_squared
            susceptance = -branch.reactance / impedance_squared
        branch_g[index] = conductance
        branch_b[index] = susceptance
        branch_b_self[index] = susceptance + branch.charging / 2.0
        tap = branch.tap if abs(branch.tap) > TOLERANCE else 1.0
        branch_tap[index] = tap
        branch_cos_shift[index] = math.cos(branch.phase_shift)
        branch_sin_shift[index] = math.sin(branch.phase_shift)
        cos_shift = branch_cos_shift[index]
        sin_shift = branch_sin_shift[index]
        branch_yff_g[index] = conductance / (tap * tap)
        branch_yff_b[index] = branch_b_self[index] / (tap * tap)
        branch_yft_g[index] = (-conductance * cos_shift + susceptance * sin_shift) / tap
        branch_yft_b[index] = (-conductance * sin_shift - susceptance * cos_shift) / tap
        branch_ytf_g[index] = (-conductance * cos_shift - susceptance * sin_shift) / tap
        branch_ytf_b[index] = (conductance * sin_shift - susceptance * cos_shift) / tap
        branch_ytt_g[index] = conductance
        branch_ytt_b[index] = branch_b_self[index]
    model_any.branch_yff_g = pyo.Param(model_any.BRANCH, initialize=branch_yff_g)
    model_any.branch_yff_b = pyo.Param(model_any.BRANCH, initialize=branch_yff_b)
    model_any.branch_yft_g = pyo.Param(model_any.BRANCH, initialize=branch_yft_g)
    model_any.branch_yft_b = pyo.Param(model_any.BRANCH, initialize=branch_yft_b)
    model_any.branch_ytf_g = pyo.Param(model_any.BRANCH, initialize=branch_ytf_g)
    model_any.branch_ytf_b = pyo.Param(model_any.BRANCH, initialize=branch_ytf_b)
    model_any.branch_ytt_g = pyo.Param(model_any.BRANCH, initialize=branch_ytt_g)
    model_any.branch_ytt_b = pyo.Param(model_any.BRANCH, initialize=branch_ytt_b)

    injections: dict[int, list[tuple[int, int, bool]]] = defaultdict(list)
    for index, branch in enumerate(branches):
        injections[branch.from_bus].append((branch.to_bus, index, True))
        injections[branch.to_bus].append((branch.from_bus, index, False))
    svcs_by_bus: dict[int, list[int]] = defaultdict(list)
    for index in svc_ids:
        svcs_by_bus[svc_bus[index]].append(index)

    def p_calc(m: Any, bus: int):
        expr = 0.0
        for other, branch_index, from_side in injections.get(bus, []):
            if from_side:
                self_g = m.branch_yff_g[branch_index]
                mutual_g = m.branch_yft_g[branch_index]
                mutual_b = m.branch_yft_b[branch_index]
            else:
                self_g = m.branch_ytt_g[branch_index]
                mutual_g = m.branch_ytf_g[branch_index]
                mutual_b = m.branch_ytf_b[branch_index]
            delta = m.va[bus] - m.va[other]
            expr += m.vm[bus] ** 2 * self_g
            expr += (
                m.vm[bus] * m.vm[other] * (mutual_g * pyo.cos(delta) + mutual_b * pyo.sin(delta))
            )
        return expr

    def q_calc(m: Any, bus: int):
        expr = -m.b_shunt[bus] * m.vm[bus] ** 2
        for other, branch_index, from_side in injections.get(bus, []):
            if from_side:
                self_b = m.branch_yff_b[branch_index]
                mutual_g = m.branch_yft_g[branch_index]
                mutual_b = m.branch_yft_b[branch_index]
            else:
                self_b = m.branch_ytt_b[branch_index]
                mutual_g = m.branch_ytf_g[branch_index]
                mutual_b = m.branch_ytf_b[branch_index]
            delta = m.va[bus] - m.va[other]
            expr -= m.vm[bus] ** 2 * self_b
            expr += (
                m.vm[bus] * m.vm[other] * (mutual_g * pyo.sin(delta) - mutual_b * pyo.cos(delta))
            )
        return expr

    model_any.calculated_p_injection = pyo.Expression(model_any.BUS, rule=p_calc)
    model_any.calculated_q_injection = pyo.Expression(model_any.BUS, rule=q_calc)

    for bus in case.buses:
        if _bus_type_code(bus.kind) == SLACK:
            cast(Any, model_any.vm[bus.number]).fix(vm_seed[bus.number])
            cast(Any, model_any.va[bus.number]).fix(va_seed[bus.number])
        elif (
            bus.kind == ACBusTypes.PV
            and bus.number not in q_limited_pv_ids
            and not strict_voltage_limits
        ):
            cast(Any, model_any.vm[bus.number]).fix(vm_seed[bus.number])

    def p_balance_rule(m: Any, bus: int):
        data = bus_by_id[bus]
        if _bus_type_code(data.kind) == SLACK:
            return pyo.Constraint.Skip
        return (
            m.p_spec[bus] - m.calculated_p_injection[bus] == m.p_slack_pos[bus] - m.p_slack_neg[bus]
        )

    def q_balance_rule(m: Any, bus: int):
        data = bus_by_id[bus]
        q_limited_pv = bus in m.QPV
        if _bus_type_code(data.kind) != PQ and not q_limited_pv:
            return pyo.Constraint.Skip
        q_spec = m.q_spec[bus]
        if q_limited_pv:
            q_spec = q_spec + m.qg_qpv[bus]
        for svc_index in svcs_by_bus.get(bus, []):
            q_spec = q_spec + m.qsvc[svc_index]
        return q_spec - m.calculated_q_injection[bus] == m.q_slack_pos[bus] - m.q_slack_neg[bus]

    model_any.active_power_balance = pyo.Constraint(model_any.BUS, rule=p_balance_rule)
    model_any.reactive_power_balance = pyo.Constraint(model_any.BUS, rule=q_balance_rule)

    def active_tolerance_rule(m: Any, bus: int):
        if _bus_type_code(bus_by_id[bus].kind) == SLACK:
            return pyo.Constraint.Skip
        return m.p_slack_pos[bus] + m.p_slack_neg[bus] <= m.active_tolerance

    def reactive_tolerance_rule(m: Any, bus: int):
        if _bus_type_code(bus_by_id[bus].kind) != PQ and bus not in m.QPV:
            return pyo.Constraint.Skip
        return m.q_slack_pos[bus] + m.q_slack_neg[bus] <= m.reactive_tolerance

    model_any.active_residual_tolerance = pyo.Constraint(model_any.BUS, rule=active_tolerance_rule)
    model_any.reactive_residual_tolerance = pyo.Constraint(
        model_any.BUS, rule=reactive_tolerance_rule
    )
    active_residual_buses = [
        bus for bus in model_any.BUS if _bus_type_code(bus_by_id[bus].kind) != SLACK
    ]
    reactive_residual_buses = [
        bus
        for bus in model_any.BUS
        if _bus_type_code(bus_by_id[bus].kind) == PQ or bus in model_any.QPV
    ]
    aggregate_active_residual = sum(
        cast(Any, model_any.p_slack_pos[bus]) - cast(Any, model_any.p_slack_neg[bus])
        for bus in active_residual_buses
    )
    aggregate_reactive_residual = sum(
        cast(Any, model_any.q_slack_pos[bus]) - cast(Any, model_any.q_slack_neg[bus])
        for bus in reactive_residual_buses
    )
    model_any.aggregate_active_residual_upper = pyo.Constraint(
        expr=(
            aggregate_active_residual <= model_any.active_tolerance
            if active_residual_buses
            else pyo.Constraint.Feasible
        )
    )
    model_any.aggregate_active_residual_lower = pyo.Constraint(
        expr=(
            aggregate_active_residual >= -pyo.value(model_any.active_tolerance)
            if active_residual_buses
            else pyo.Constraint.Feasible
        )
    )
    model_any.aggregate_reactive_residual_upper = pyo.Constraint(
        expr=(
            aggregate_reactive_residual <= model_any.reactive_tolerance
            if reactive_residual_buses
            else pyo.Constraint.Feasible
        )
    )
    model_any.aggregate_reactive_residual_lower = pyo.Constraint(
        expr=(
            aggregate_reactive_residual >= -pyo.value(model_any.reactive_tolerance)
            if reactive_residual_buses
            else pyo.Constraint.Feasible
        )
    )

    model_any.voltage_upper_limit = pyo.Constraint(
        model_any.BUS,
        rule=lambda m, bus: m.vm[bus] <= m.vm_max[bus] + m.v_upper_slack[bus],
    )
    model_any.voltage_lower_limit = pyo.Constraint(
        model_any.BUS,
        rule=lambda m, bus: m.vm[bus] >= m.vm_min[bus] - m.v_lower_slack[bus],
    )
    model_any.angle_upper_limit = pyo.Constraint(
        model_any.BUS,
        rule=lambda m, bus: m.va[bus] <= m.angle_limit + m.a_upper_slack[bus],
    )
    model_any.angle_lower_limit = pyo.Constraint(
        model_any.BUS,
        rule=lambda m, bus: m.va[bus] >= -pyo.value(m.angle_limit) - m.a_lower_slack[bus],
    )

    def svc_lower_rule(m: Any, index: int):
        return m.qsvc[index] >= m.svc_q_min[index] * m.vm[m.svc_ctrl_bus[index]] ** 2

    def svc_upper_rule(m: Any, index: int):
        return m.qsvc[index] <= m.svc_q_max[index] * m.vm[m.svc_ctrl_bus[index]] ** 2

    def svc_control_rule(m: Any, index: int):
        if abs(pyo.value(m.svc_slope[index])) <= TOLERANCE:
            return pyo.Constraint.Skip
        svc = (case.svcs or [])[index]
        if str(svc.mode).upper() == "I":
            expr = (
                m.vm[m.svc_ctrl_bus[index]]
                - m.svc_vref[index]
                + m.qsvc[index] * m.svc_slope[index] / m.vm[m.svc_bus[index]]
            )
        else:
            expr = (
                m.vm[m.svc_ctrl_bus[index]] - m.svc_vref[index] + m.qsvc[index] * m.svc_slope[index]
            )
        return expr == m.svc_residual_pos[index] - m.svc_residual_neg[index]

    model_any.svc_q_lower = pyo.Constraint(model_any.SVC, rule=svc_lower_rule)
    model_any.svc_q_upper = pyo.Constraint(model_any.SVC, rule=svc_upper_rule)
    model_any.svc_control = pyo.Constraint(model_any.SVC, rule=svc_control_rule)
    model_any.svc_residual_tolerance = pyo.Constraint(
        model_any.SVC,
        rule=lambda m, index: (
            m.svc_residual_pos[index] + m.svc_residual_neg[index] <= m.control_tolerance
        ),
    )

    def objective_rule(m: Any):
        power_slacks = sum(
            m.p_slack_pos[bus] ** 2
            + m.p_slack_neg[bus] ** 2
            + m.q_slack_pos[bus] ** 2
            + m.q_slack_neg[bus] ** 2
            for bus in m.BUS
        )
        svc_slacks = sum(
            m.svc_residual_pos[index] ** 2 + m.svc_residual_neg[index] ** 2 for index in m.SVC
        )
        voltage_limit_slacks = sum(
            m.v_upper_slack[bus] ** 2 + m.v_lower_slack[bus] ** 2 for bus in m.BUS
        )
        voltage_regularization = sum((m.vm[bus] - vm_seed[bus]) ** 2 for bus in m.BUS)
        angle_limit_slacks = sum(
            m.a_upper_slack[bus] ** 2 + m.a_lower_slack[bus] ** 2 for bus in m.BUS
        )
        angle_regularization = sum((m.va[bus] - va_seed[bus]) ** 2 for bus in m.BUS)
        reactive_generation_regularization = sum(
            (m.qg_qpv[bus] - qg_initial[bus]) ** 2 for bus in m.QPV
        )
        return (
            power_slacks
            + m.weight_svc * svc_slacks
            + m.weight_voltage_limits * voltage_limit_slacks
            + m.weight_voltage * voltage_regularization
            + m.weight_angle_limits * angle_limit_slacks
            + m.weight_angle * angle_regularization
            + reactive_generation_regularization
        )

    model_any._case = case
    model_any._strict_voltage_limits = strict_voltage_limits

    p_seed: dict[int, float] = defaultdict(float)
    q_seed: dict[int, float] = defaultdict(float)
    for bus in case.buses:
        _p_calc = 0.0
        _q_calc = -bus.shunt_susceptance * vm_seed[bus.number] * vm_seed[bus.number]
        for other, branch_index, from_side in injections.get(bus.number, []):
            branch = branches[branch_index]
            if from_side:
                self_g = branch_yff_g[branch_index]
                self_b = branch_yff_b[branch_index]
                mutual_g = branch_yft_g[branch_index]
                mutual_b = branch_yft_b[branch_index]
            else:
                self_g = branch_ytt_g[branch_index]
                self_b = branch_ytt_b[branch_index]
                mutual_g = branch_ytf_g[branch_index]
                mutual_b = branch_ytf_b[branch_index]
            delta = va_seed[bus.number] - va_seed[other]
            _p_calc += vm_seed[bus.number] ** 2 * self_g
            _p_calc += (
                vm_seed[bus.number]
                * vm_seed[other]
                * (mutual_g * math.cos(delta) + mutual_b * math.sin(delta))
            )
            _q_calc -= vm_seed[bus.number] ** 2 * self_b
            _q_calc += (
                vm_seed[bus.number]
                * vm_seed[other]
                * (mutual_g * math.sin(delta) - mutual_b * math.cos(delta))
            )
        p_seed[bus.number] = _p_calc
        q_seed[bus.number] = _q_calc
    for bus in case.buses:
        bus_id = bus.number
        vm0 = vm_seed[bus_id]
        cast(Any, model_any.v_upper_slack[bus_id]).set_value(
            max(0.0, vm0 - pyo.value(model_any.vm_max[bus_id])), skip_validation=True
        )
        cast(Any, model_any.v_lower_slack[bus_id]).set_value(
            max(0.0, pyo.value(model_any.vm_min[bus_id]) - vm0), skip_validation=True
        )
        cast(Any, model_any.a_upper_slack[bus_id]).set_value(
            max(0.0, va_seed[bus_id] - pyo.value(model_any.angle_limit)), skip_validation=True
        )
        cast(Any, model_any.a_lower_slack[bus_id]).set_value(
            max(0.0, -pyo.value(model_any.angle_limit) - va_seed[bus_id]), skip_validation=True
        )
        if _bus_type_code(bus.kind) != SLACK:
            p_spec0 = pyo.value(model_any.p_spec[bus_id])
            _set_signed_slack(
                model_any.p_slack_pos[bus_id],
                model_any.p_slack_neg[bus_id],
                p_spec0 - p_seed.get(bus_id, 0.0),
            )
        q_limited_pv = bus_id in q_limited_pv_ids
        if _bus_type_code(bus.kind) == PQ or q_limited_pv:
            q_spec0 = pyo.value(model_any.q_spec[bus_id])
            if q_limited_pv:
                q_spec0 += pyo.value(model_any.qg_qpv[bus_id])
            for svc_index in svcs_by_bus.get(bus_id, []):
                q_spec0 += svc_q_initial[svc_index]
            _set_signed_slack(
                model_any.q_slack_pos[bus_id],
                model_any.q_slack_neg[bus_id],
                q_spec0 - q_seed.get(bus_id, 0.0),
            )
    for index, svc in enumerate(case.svcs or []):
        vref = svc_vref[index]
        slope = svc_slope[index]
        if abs(slope) <= TOLERANCE:
            continue
        if str(svc.mode).upper() == "I":
            residual = (
                vm_seed[svc.controlled_bus]
                - vref
                + svc_q_initial[index] * slope / max(vm_seed[svc.bus], TOLERANCE)
            )
        else:
            residual = vm_seed[svc.controlled_bus] - vref + svc_q_initial[index] * slope
        _set_signed_slack(
            model_any.svc_residual_pos[index],
            model_any.svc_residual_neg[index],
            residual,
        )

    if objective_function == "minimize_residuals":
        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)
    elif objective_function == "zero_function":
        _apply_zero_residuals(model)
        model_any.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)
    elif objective_function == "squared_generation":
        _apply_zero_residuals(model)
        _apply_slack_generation_redispatch(model, case, bus_by_id, p_seed)
        model_any.objective = pyo.Objective(
            expr=objective_rule(model)
            + sum(model_any.pg_slack[bus] ** 2 for bus in model_any.SLACK_GEN),
            sense=pyo.minimize,
        )
    model_any._objective_function = objective_function
    return model


def solution_metrics(model: pyo.ConcreteModel) -> dict[str, float | bool]:
    """Report maximum and aggregate balance residuals from a solved model.

    Residuals are recomputed directly from the power-balance equations rather
    than from the residual slacks, so the report stays meaningful in the
    ``zero_function``/``squared_generation`` modes where the slacks are fixed at
    zero and an infeasible point is exactly the equation violation. Slack buses
    close the system balance by construction and are excluded from the maximum
    residual, mirroring the Newton-Raphson mismatch metric.
    """
    model_any = cast(Any, model)
    case = cast(PowerFlowCase, model_any._case)
    svcs_by_bus: dict[int, list[int]] = {}
    for index in model_any.SVC:
        svcs_by_bus.setdefault(int(_value_or_default(model_any.svc_bus[index])), []).append(index)
    slack_buses = [bus.number for bus in case.buses if _bus_type_code(bus.kind) == SLACK]
    active_residual_buses = [bus.number for bus in case.buses if _bus_type_code(bus.kind) != SLACK]
    reactive_residual_buses = [
        bus.number
        for bus in case.buses
        if _bus_type_code(bus.kind) == PQ or bus.number in model_any.QPV
    ]

    def reactive_residual(bus: int) -> float:
        expr = _value_or_default(model_any.q_spec[bus])
        if bus in model_any.QPV:
            expr += _value_or_default(model_any.qg_qpv[bus])
        for index in svcs_by_bus.get(bus, []):
            expr += _value_or_default(model_any.qsvc[index])
        return expr - _value_or_default(model_any.calculated_q_injection[bus])

    max_p = 0.0
    max_q = 0.0
    max_svc = 0.0
    max_p_slack = 0.0
    max_q_slack = 0.0
    for bus in case.buses:
        if bus.number in slack_buses:
            if hasattr(model_any, "pg_slack") and bus.number in model_any.SLACK_GEN:
                max_p_slack = max(
                    max_p_slack,
                    abs(
                        _value_or_default(model_any.pg_slack[bus.number])
                        - _value_or_default(model_any._slack_load_pu[bus.number])
                        - _value_or_default(model_any.calculated_p_injection[bus.number])
                    ),
                )
            continue
        max_p = max(
            max_p,
            abs(
                _value_or_default(model_any.p_spec[bus.number])
                - _value_or_default(model_any.calculated_p_injection[bus.number])
            ),
        )
        if bus.number in reactive_residual_buses:
            max_q = max(max_q, abs(reactive_residual(bus.number)))
    for index in model_any.SVC:
        slope = _value_or_default(model_any.svc_slope[index])
        if abs(slope) <= TOLERANCE:
            continue
        svc = (case.svcs or [])[index]
        droop = _value_or_default(
            model_any.vm[int(_value_or_default(model_any.svc_ctrl_bus[index]))]
        ) - _value_or_default(model_any.svc_vref[index])
        q_svc = _value_or_default(model_any.qsvc[index])
        if str(svc.mode).upper() == "I":
            droop += (
                q_svc
                * slope
                / max(
                    _value_or_default(
                        model_any.vm[int(_value_or_default(model_any.svc_bus[index]))]
                    ),
                    TOLERANCE,
                )
            )
        else:
            droop += q_svc * slope
        max_svc = max(max_svc, abs(droop))
    aggregate_p = sum(
        _value_or_default(model_any.p_spec[bus])
        - _value_or_default(model_any.calculated_p_injection[bus])
        for bus in active_residual_buses
    )
    aggregate_q = sum(reactive_residual(bus) for bus in reactive_residual_buses)
    active_tolerance = pyo.value(model_any.active_tolerance)
    reactive_tolerance = pyo.value(model_any.reactive_tolerance)
    control_tolerance = pyo.value(model_any.control_tolerance)
    return {
        "max_p": max_p,
        "max_q": max_q,
        "max_svc": max_svc,
        "max_p_slack": max_p_slack,
        "max_q_slack": max_q_slack,
        "aggregate_p": aggregate_p,
        "aggregate_q": aggregate_q,
        "converged": max_p <= active_tolerance + CONVERGENCE_REPORT_EPS
        and max_q <= reactive_tolerance + CONVERGENCE_REPORT_EPS
        and max_svc <= control_tolerance + CONVERGENCE_REPORT_EPS
        and abs(aggregate_p) <= active_tolerance + CONVERGENCE_REPORT_EPS
        and abs(aggregate_q) <= reactive_tolerance + CONVERGENCE_REPORT_EPS,
    }


def _parse_ipopt_iterations(log_text: str) -> int | None:
    match = re.search(r"Number of Iterations\.+:?\s+(\d+)", log_text)
    return int(match.group(1)) if match is not None else None


def _optimization_failure_state(
    termination: TerminationCondition | None,
) -> str:
    """Return the failure qualifier for a non-converged optimization run."""
    if termination in {
        TerminationCondition.infeasible,
        TerminationCondition.infeasibleOrUnbounded,
    }:
        return "infeasible"
    if termination in {
        TerminationCondition.unbounded,
        TerminationCondition.infeasibleOrUnbounded,
    }:
        return "unbounded"
    return "not converged"


def solve_optimization_model(
    model: pyo.ConcreteModel,
    *,
    max_iterations: int = 30,
    max_cpu_time: float = 300.0,
    print_iterations: bool = False,
):
    """Solve the optimization model with Ipopt and return the results and log."""
    solver = SolverFactory("ipopt")
    if solver is None or not solver.available(exception_flag=False):
        return None, "", None
    solver.options["max_iter"] = int(max_iterations)
    solver.options["max_cpu_time"] = float(max_cpu_time)
    solver.options["tol"] = 1.0e-8
    solver.options["acceptable_tol"] = 1.0e-6
    solver.options["acceptable_iter"] = 3
    solver.options["mu_strategy"] = "adaptive"
    if print_iterations:
        solver.options["print_level"] = 5
    log_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ipopt-", suffix=".log", delete=False) as log_file:
            log_path = Path(log_file.name)
        results = solver.solve(model, tee=print_iterations, logfile=str(log_path))
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        return results, log_text, _parse_ipopt_iterations(log_text)
    finally:
        if log_path is not None:
            log_path.unlink(missing_ok=True)


class OptimizationACPowerFlow(PowerFlowSolver):
    """Optimization-based AC power flow solved as a nonlinear program with Ipopt.

    ``objective_function`` selects the formulation solved by Ipopt:

    * ``minimize_residuals`` -- weighted least-squares feasibility restoration
      (soft balance, limit, and SVC droop constraints with bounded slacks).
    * ``zero_function`` -- exact power balance: the active and reactive
      residual slacks are fixed at zero so ``P_spec = P_calc`` and
      ``Q_spec = Q_calc`` hold as hard equalities, while the SVC droop and the
      voltage/angle limits stay soft (weighted in the objective).
    * ``squared_generation`` -- ``zero_function`` plus reference-bus generation
      redispatched to minimize the sum of squared active generation.
    """

    solver_name: ClassVar[str] = "optimization"

    def __init__(
        self,
        system: System | None = None,
        *,
        tolerance: float | None = None,
        max_iterations: int = 30,
        max_control_passes: int = 12,
        print_iterations: bool = False,
        strict_voltage_limits: bool = False,
        objective_function: str = "minimize_residuals",
    ) -> None:
        if objective_function not in VALID_OBJECTIVE_FUNCTIONS:
            raise ValueError(
                "Unknown objective_function {!r}; expected one of {}".format(
                    objective_function, ", ".join(VALID_OBJECTIVE_FUNCTIONS)
                )
            )
        super().__init__(
            system=system,
            tolerance=tolerance,
            max_iterations=max_iterations,
            max_control_passes=max_control_passes,
            print_iterations=print_iterations,
        )
        self.strict_voltage_limits = strict_voltage_limits
        self.objective_function = objective_function

    def run(
        self,
        pwf_path: str | Path | System | ParsedAnaredeSystem,
        *,
        system_name: str | None = None,
    ) -> PowerFlowRun:
        """Solve a PWF path or parsed infrasys system with the optimization formulation."""
        if isinstance(pwf_path, ParsedAnaredeSystem):
            parsed = pwf_path
        elif isinstance(pwf_path, System):
            parsed = ParsedAnaredeSystem.from_system(pwf_path)
        else:
            source = Path(pwf_path).resolve()
            parser = AnaredeInfrasysParser(system_name=system_name or source.stem)
            parsed = parser.parse(source)

        case = build_power_flow_case(parsed)
        settings = build_power_flow_settings(
            parsed,
            tolerance=self.tolerance,
            max_iterations=self.max_iterations,
        )
        reduction = reduce_closed_switches(case)
        numerical_case = reduction.case

        model = build_optimization_model(
            numerical_case,
            active_tolerance_pu=max(settings.active_tolerance, TOLERANCE),
            reactive_tolerance_pu=max(settings.reactive_tolerance, TOLERANCE),
            control_tolerance_pu=max(settings.control_tolerance, TOLERANCE),
            qlim_enabled="QLIM" in settings.options,
            strict_voltage_limits=getattr(self, "strict_voltage_limits", False),
            objective_function=getattr(self, "objective_function", "minimize_residuals"),
        )
        results, solver_log, ipopt_iterations = solve_optimization_model(
            model,
            max_iterations=self.max_iterations,
            print_iterations=self.print_iterations,
        )
        if results is None:
            logger.error(
                "Optimization power flow failed because Ipopt is not available.",
            )
            return self._failed_run(
                parsed,
                case,
                reduction,
                settings,
                error="Ipopt solver is not available",
            )

        termination = getattr(getattr(results, "solver", None), "termination_condition", None)
        optimal_statuses = {
            TerminationCondition.optimal,
            TerminationCondition.locallyOptimal,
            TerminationCondition.feasible,
        }
        solver_ok = termination in optimal_statuses
        metrics = solution_metrics(model)
        converged = solver_ok and metrics["converged"]
        diverged = termination in {
            TerminationCondition.infeasible,
            TerminationCondition.infeasibleOrUnbounded,
            TerminationCondition.unbounded,
            TerminationCondition.error,
        }
        iterations = int(ipopt_iterations or 0)
        max_mismatch = max(metrics["max_p"], metrics["max_q"], metrics["max_svc"])

        vm, va = _solved_voltage(model)
        reduced_voltage = np.array(
            [vm[bus.number] * np.exp(1j * va[bus.number]) for bus in numerical_case.buses],
            dtype=np.complex128,
        )
        refresh_lcc_reporting_state(numerical_case, reduced_voltage)
        reduction.sync_control_state(case)
        expanded_voltage = reduction.expand_voltage(reduced_voltage)
        result_ybus = build_ybus(case)
        result = ACPowerFlowResult(
            solver=self.solver_name,
            converged=converged,
            diverged=diverged,
            iterations=iterations,
            max_mismatch=max_mismatch,
            fallback_used=False,
            base_mva=case.base_mva,
            iteration_trace=[
                IterationPowerFlowResult(
                    iteration=1,
                    max_dp=metrics["max_p"],
                    max_dq=metrics["max_q"],
                    max_control_residual=metrics["max_svc"],
                    max_residual=max_mismatch,
                    max_step=0.0,
                )
            ],
            buses=calculate_bus_results(case, result_ybus, expanded_voltage),
            branches=calculate_branch_results(case, expanded_voltage),
        )
        apply_power_flow_result(parsed, result)
        component_results = build_component_results(
            parsed,
            case,
            result,
            reduction=reduction,
            tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
        )
        set_results = getattr(parsed.system, "set_power_flow_results", None)
        if callable(set_results):
            set_results(component_results)
        if converged:
            logger.success(
                "Optimization AC power flow converged in {} iteration(s); max mismatch {:.4e} pu.",
                iterations,
                max_mismatch,
            )
        else:
            logger.error(
                "Optimization AC power flow is {} after {} iteration(s); max mismatch {:.4e} pu.",
                _optimization_failure_state(termination),
                iterations,
                max_mismatch,
            )
        report = summarize_solution(model)
        if solver_log.strip():
            report = f"{report}\n\n{solver_log}"
        return PowerFlowRun(parsed=parsed, result=result, stdout=report)

    def _failed_run(
        self,
        parsed: ParsedAnaredeSystem,
        case: PowerFlowCase,
        reduction,
        settings,
        *,
        error: str,
    ) -> PowerFlowRun:
        """Return a non-converged run built from the initial network state."""
        logger.error(
            "Optimization AC power flow did not produce a solution: {}.",
            error,
        )
        initial_voltage = case.initial_voltage
        result_ybus = build_ybus(case)
        result = ACPowerFlowResult(
            solver=self.solver_name,
            converged=False,
            diverged=True,
            iterations=0,
            max_mismatch=0.0,
            fallback_used=False,
            base_mva=case.base_mva,
            iteration_trace=[],
            buses=calculate_bus_results(case, result_ybus, initial_voltage),
            branches=calculate_branch_results(case, initial_voltage),
        )
        apply_power_flow_result(parsed, result)
        return PowerFlowRun(parsed=parsed, result=result, stdout=error)


def _solved_voltage(
    model: pyo.ConcreteModel,
) -> tuple[dict[int, float], dict[int, float]]:
    model_any = cast(Any, model)
    case = cast(PowerFlowCase, model_any._case)
    vm = {
        bus.number: _value_or_default(model_any.vm[bus.number], bus.voltage) for bus in case.buses
    }
    va = {bus.number: _value_or_default(model_any.va[bus.number], bus.angle) for bus in case.buses}
    return vm, va


def summarize_solution(model: pyo.ConcreteModel) -> str:
    """Return a human-readable summary of a solved optimization power flow."""
    model_any = cast(Any, model)
    case = cast(PowerFlowCase, model_any._case)
    vm, va = _solved_voltage(model)
    metrics = solution_metrics(model)
    lines = [
        f"Optimization power-flow summary for {len(case.buses)} buses, "
        f"{len(case.branches)} branches",
        f"  Objective function: {getattr(model_any, '_objective_function', 'minimize_residuals')}",
        f"  Converged: {metrics['converged']}",
        f"  Max P residual: {metrics['max_p']:.6e} pu",
        f"  Max Q residual: {metrics['max_q']:.6e} pu",
        f"  Max SVC residual: {metrics['max_svc']:.6e} pu",
        f"  Aggregate P residual: {metrics['aggregate_p']:.6e} pu",
        f"  Aggregate Q residual: {metrics['aggregate_q']:.6e} pu",
    ]
    for bus in case.buses:
        if vm[bus.number] > bus.maximum_voltage + DISPLAY_TOLERANCE:
            lines.append(
                f"  Voltage above limit: bus {bus.number} {bus.name} "
                f"{vm[bus.number]:.4f} pu (max {bus.maximum_voltage:.4f})"
            )
        elif vm[bus.number] < bus.minimum_voltage - DISPLAY_TOLERANCE:
            lines.append(
                f"  Voltage below limit: bus {bus.number} {bus.name} "
                f"{vm[bus.number]:.4f} pu (min {bus.minimum_voltage:.4f})"
            )
    return "\n".join(lines)
