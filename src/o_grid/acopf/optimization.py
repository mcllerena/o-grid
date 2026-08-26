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
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import numpy as np
import pyomo.environ as pyo
from infrasys import System
from loguru import logger
from pyomo.opt import SolverFactory, TerminationCondition

from o_grid.acpf.models import (
    ReducedPowerFlowCase,
    build_component_results,
    build_power_flow_case,
    build_power_flow_settings,
    reduce_closed_switches,
)
from o_grid.acpf.models.case import BusData, PowerFlowCase
from o_grid.acpf.models.lcc import refresh_lcc_reporting_state
from o_grid.acpf.models.svc import clamp_svc_seed_to_limits
from o_grid.acpf.newton_raphson import solve_newton_raphson
from o_grid.acpf.results import (
    ACPowerFlowResult,
    IterationPowerFlowResult,
    PowerFlowRun,
    apply_power_flow_result,
)
from o_grid.acpf.solver import PowerFlowSolver
from o_grid.acpf.utils import (
    assign_island_reference_buses,
    build_ybus,
    calculate_branch_results,
    calculate_bus_results,
)
from o_grid.formulations import resolve_formulation
from o_grid.formulations.conic import ConicModel, build_conic_model, solve_conic_model
from o_grid.formulations.current_voltage import (
    add_ivr_branch_equations,
    add_ivr_variables,
)
from o_grid.formulations.current_voltage import (
    branch_power as ivr_branch_power,
)
from o_grid.formulations.lifted import (
    add_act_voltage_variables,
)
from o_grid.formulations.lifted import (
    branch_power as act_branch_power,
)
from o_grid.formulations.lifted import (
    p_injection as act_p_injection,
)
from o_grid.formulations.lifted import (
    q_injection as act_q_injection,
)
from o_grid.formulations.linear import (
    branch_power as linear_branch_power,
)
from o_grid.formulations.linear import (
    p_injection as linear_p_injection,
)
from o_grid.formulations.rectangular import (
    add_acr_voltage_variables,
    branch_power,
    p_injection,
    q_injection,
)
from o_grid.models import ACBusTypes
from o_grid.solvers import ClarabelBridge
from o_grid.statics.pwf_parser import AnaredeInfrasysParser, ParsedAnaredeSystem

TOLERANCE = 1.0e-12
DISPLAY_TOLERANCE = 1.0e-9
CONVERGENCE_REPORT_EPS = 1.0e-6
CONIC_FORMULATIONS = {
    "SOCWRPowerModel",
    "SOCWRConicPowerModel",
    "SOCBFPowerModel",
    "SOCBFConicPowerModel",
    "SDPWRMPowerModel",
    "SparseSDPWRMPowerModel",
}
ANGLE_LIMIT_RAD = math.pi / 2.0
ANGLE_BOUND_RAD = math.pi
LINEAR_FORMULATIONS = {
    "DCPPowerModel",
    "DCMPPowerModel",
    "BFAPowerModel",
    "NFAPowerModel",
}

OBJECTIVE_WEIGHT_VOLTAGE = 1.0
OBJECTIVE_WEIGHT_VOLTAGE_LIMITS = 100.0
OBJECTIVE_WEIGHT_ANGLE = 1.0
OBJECTIVE_WEIGHT_ANGLE_LIMITS = 1.0e-2
OBJECTIVE_WEIGHT_LTC = 0.01
OBJECTIVE_WEIGHT_SVC = 100.0

VALID_OBJECTIVE_FUNCTIONS = (
    "voltage_deviation",
)

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


def _is_ltc_branch(branch_index: int, branch: object) -> bool:
    return (
        getattr(branch, "controlled_bus", None) is not None
        and getattr(branch, "minimum_tap", 0.0) > 0.0
        and getattr(branch, "maximum_tap", 0.0) > getattr(branch, "minimum_tap", 0.0)
        and abs(getattr(branch, "phase_shift", 0.0)) <= TOLERANCE
    )


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
    deactivated. SVC droop residuals stay in the objective (their hard
    control-tolerance row is removed from the formulation entirely) and the
    voltage/angle limits stay soft: those are control targets and operational
    bounds, not physical equations, and leaving them relaxed keeps the
    exact-balance model feasible on cases that only converge inside a tolerance
    band (e.g. ``CASO_FINAL_EQV2020``).
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


def _apply_exact_power_flow(model: pyo.ConcreteModel) -> None:
    """Enforce the AC power-flow equations exactly and relax operational limits.

    The power-balance slacks are already fixed at zero by
    :func:`_apply_zero_residuals`.  This helper deactivates the voltage and
    angle limit rows (an AC power flow reports operational limits instead of
    enforcing them) and pins their slacks to zero so the deactivated rows carry
    no degrees of freedom.  The SVC droop and LTC voltage-control residuals are
    left free: the droop row is then soft and a control device sitting at a
    reactive or tap limit can release its controller equation without making
    the exact-balance model infeasible.
    """
    for component_name in ("v_upper_slack", "v_lower_slack", "a_upper_slack", "a_lower_slack"):
        component = getattr(model, component_name)
        for index in component:
            component[index].fix(0.0)
    for component_name in (
        "voltage_upper_limit",
        "voltage_lower_limit",
        "angle_upper_limit",
        "angle_lower_limit",
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


def _newton_warm_start(case: PowerFlowCase, settings) -> bool:
    """Seed the case buses with a Newton-Raphson solution when available.

    The optimization NLP is sensitive to its seed operating point.  A solved
    case already satisfies the balance equations and releases saturated SVC
    droop rows, giving Ipopt a feasible neighborhood to start from, whereas the
    raw ANAREDE seed is often an internally inconsistent operating snapshot.
    When Newton-Raphson does not fully converge but improves the residual
    without diverging, its final iterate is still written back: the active rows
    are typically converged and only a reactive limit cycle remains, which is a
    far better starting point for the NLP than the raw input seed.  Island
    reference buses are assigned exactly as in the Newton-Raphson solver path
    and stay assigned, so islands whose input data lacks a reference bus are
    solved the same way in the optimization model.  Returns ``True`` when the
    NR solution is written back into the case buses; otherwise the case is left
    untouched and the caller keeps the input seed.
    """
    original_kinds = [bus.kind for bus in case.buses]
    try:
        ybus = build_ybus(case)
        assign_island_reference_buses(case, ybus)
        solution = solve_newton_raphson(
            case,
            ybus,
            tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
            max_iterations=int(getattr(settings, "max_iterations", 30)),
        )
    except Exception:
        for bus, kind in zip(case.buses, original_kinds):
            bus.kind = kind
        return False
    if solution.diverged or not solution.trace:
        for bus, kind in zip(case.buses, original_kinds):
            bus.kind = kind
        return False
    initial_residual = solution.trace[0].max_residual
    if (
        not solution.converged
        and solution.max_mismatch is not None
        and solution.max_mismatch >= initial_residual
    ):
        for bus, kind in zip(case.buses, original_kinds):
            bus.kind = kind
        return False
    for bus, voltage in zip(case.buses, solution.voltage):
        bus.voltage = float(abs(voltage))
        bus.angle = float(np.angle(voltage))
    return True


def build_optimization_model(
    case: PowerFlowCase,
    *,
    active_tolerance_pu: float,
    reactive_tolerance_pu: float,
    control_tolerance_pu: float,
    qlim_enabled: bool = False,
    strict_voltage_limits: bool = False,
    objective_function: str = "voltage_deviation",
    formulation: str = "ACPPowerModel",
    optimize_ltc_taps: bool = False,
    optimize_ltc_controls: bool = False,
    enforce_shunt_deadbands: bool = False,
) -> pyo.ConcreteModel | ConicModel:
    """Build and initialize the Pyomo AC power-flow optimization model.

    ``objective_function`` selects which formulation is instantiated:

    * ``minimize_residuals`` -- the default feasibility-restoration model.  All
      physical and controller equations are soft constraints whose positive and
      negative slacks are bounded by the per-bus tolerances, and the objective
      minimizes the weighted sum of squared slacks plus a small regularization
      toward the input state.  The SVC droop row is a soft control with no hard
      residual cap: the objective drives it to zero while the device has
      reactive headroom, and the droop error is carried as an objective
      contribution when the device saturates at a capability limit.
    * ``zero_function`` -- the classic AC power flow.  The active and reactive
      power-balance equations hold as hard equalities (their slacks are fixed
      at zero) while the operational voltage and angle limits are relaxed, so
      the objective is identically zero and Ipopt performs a pure feasibility
      solve of the power-flow equations.  SVC/LTC droop residuals stay soft so
      a saturated controller can release its row without making the exact
      balance model infeasible.
    * ``squared_generation`` -- exact power balance with free reference-bus
      active generation and an objective that minimizes the sum of squared
      active generation, selecting the feasible point with minimum generation
      (equivalently minimum losses for a fixed load).
        * ``voltage_deviation`` -- security-constrained ACOPF.  Voltage,
            nodal-balance, phase-angle, and branch thermal limits are hard; the
                    objective minimizes the squared active-generation dispatch fallback.
    """
    selected_formulation = resolve_formulation(formulation)
    if not selected_formulation.implemented:
        raise NotImplementedError(
            f"ACOPF formulation {selected_formulation.name!r} is registered but not implemented"
        )
    if objective_function not in VALID_OBJECTIVE_FUNCTIONS:
        raise ValueError(
            "Unknown objective_function {!r}; expected one of {}".format(
                objective_function, ", ".join(VALID_OBJECTIVE_FUNCTIONS)
            )
            )
    if selected_formulation.name in CONIC_FORMULATIONS:
        model = build_conic_model(case, selected_formulation.name)
        cast(Any, model)._objective_function = objective_function
        return model
    model = pyo.ConcreteModel("optimization_power_flow")
    model_any = cast(Any, model)
    model_any._case = case
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
    hard_security = True
    model_any._hard_security = hard_security
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
    model_any.weight_ltc = pyo.Param(initialize=OBJECTIVE_WEIGHT_LTC)
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

    security_generator_ids = [
        bus.number
        for bus in case.buses
        if objective_function == "voltage_deviation"
        and (
            abs(bus.active_generation) > TOLERANCE
            or abs(bus.reactive_generation) > TOLERANCE
            or _bus_type_code(bus.kind) == SLACK
        )
    ]
    security_pg_initial = {
        bus.number: bus.active_generation / base_mva
        for bus in case.buses
        if bus.number in security_generator_ids
    }
    security_pg_bounds = {
        bus.number: (
            0.0,
            max(
                2.0 * abs(bus.active_generation),
                abs(bus.active_load) + base_mva,
                base_mva,
            )
            / base_mva,
        )
        for bus in case.buses
        if bus.number in security_generator_ids
    }
    model_any.security_generator_ids = pyo.Set(
        initialize=security_generator_ids, ordered=True
    )
    model_any.pg_security = pyo.Var(
        model_any.security_generator_ids,
        initialize=security_pg_initial,
        bounds=lambda m, bus: security_pg_bounds[bus],
        within=pyo.NonNegativeReals,
    )
    security_qg_bounds = {
        bus.number: (
            (
                bus.minimum_reactive_generation
                if bus.minimum_reactive_generation is not None
                else -max(abs(bus.reactive_generation), base_mva)
            )
            / base_mva,
            (
                bus.maximum_reactive_generation
                if bus.maximum_reactive_generation is not None
                else max(abs(bus.reactive_generation), base_mva)
            )
            / base_mva,
        )
        for bus in case.buses
        if bus.number in security_generator_ids
    }
    security_qg_initial = {
        bus.number: min(
            max(bus.reactive_generation / base_mva, security_qg_bounds[bus.number][0]),
            security_qg_bounds[bus.number][1],
        )
        for bus in case.buses
        if bus.number in security_generator_ids
    }
    model_any.qg_security = pyo.Var(
        model_any.security_generator_ids,
        initialize=security_qg_initial,
        bounds=lambda m, bus: security_qg_bounds[bus],
        within=pyo.Reals,
    )

    lcc_indices = [
        index
        for index, lcc in enumerate(case.lccs or [])
        if lcc.pdc_mw > TOLERANCE
        and lcc.vbase_kv > TOLERANCE
        and lcc.vdc_rectifier_kv > TOLERANCE
        and lcc.vdc_inverter_kv > TOLERANCE
    ]
    lcc_data = [(case.lccs or [])[index] for index in lcc_indices]
    lcc_ids = list(range(len(lcc_data)))
    model_any.LCC = pyo.Set(initialize=lcc_ids, ordered=True)
    lcc_rectifier_bus = {index: lcc.rectifier_bus for index, lcc in enumerate(lcc_data)}
    lcc_inverter_bus = {index: lcc.inverter_bus for index, lcc in enumerate(lcc_data)}
    lcc_power_initial = {index: lcc.pdc_mw / base_mva for index, lcc in enumerate(lcc_data)}
    lcc_power_max = {
        index: max(1.5 * value, value + 1.0) for index, value in lcc_power_initial.items()
    }
    lcc_vdc_rect_initial = {index: lcc.vdc_rectifier_kv for index, lcc in enumerate(lcc_data)}
    lcc_vdc_inv_initial = {index: lcc.vdc_inverter_kv for index, lcc in enumerate(lcc_data)}
    lcc_rdc = {}
    lcc_rectifier_gain = {}
    lcc_inverter_gain = {}
    lcc_rectifier_q_factor = {}
    lcc_inverter_q_factor = {}
    for index, lcc in enumerate(lcc_data):
        vrect = max(lcc.vdc_rectifier_kv / max(lcc.vbase_kv, 1.0), 1.0e-6)
        vinv = max(lcc.vdc_inverter_kv / max(lcc.vbase_kv, 1.0), 1.0e-6)
        pdc = max(lcc.pdc_mw / base_mva, 1.0e-6)
        current = pdc / vrect
        lcc_rdc[index] = max((vrect - vinv) / max(current, 1.0e-6), 0.0)
        lcc_rectifier_gain[index] = vrect
        lcc_inverter_gain[index] = vinv
        lcc_rectifier_q_factor[index] = lcc.q_rectifier_mvar / base_mva / pdc
        lcc_inverter_q_factor[index] = lcc.q_inverter_mvar / base_mva / pdc
    lcc_vbase = {index: max(lcc.vbase_kv, 1.0) for index, lcc in enumerate(lcc_data)}
    lcc_alpha_initial = {index: math.radians(lcc.alpha_deg) for index, lcc in enumerate(lcc_data)}
    lcc_gamma_initial = {index: math.radians(lcc.gamma_deg) for index, lcc in enumerate(lcc_data)}
    lcc_q_rect_initial = {
        index: lcc.q_rectifier_mvar / base_mva for index, lcc in enumerate(lcc_data)
    }
    lcc_q_inv_initial = {
        index: lcc.q_inverter_mvar / base_mva for index, lcc in enumerate(lcc_data)
    }
    lcc_p_rect_initial = {
        index: lcc.p_rectifier_mw / base_mva for index, lcc in enumerate(lcc_data)
    }
    lcc_p_inv_initial = {index: lcc.p_inverter_mw / base_mva for index, lcc in enumerate(lcc_data)}
    model_any.lcc_rectifier_bus = pyo.Param(model_any.LCC, initialize=lcc_rectifier_bus)
    model_any.lcc_inverter_bus = pyo.Param(model_any.LCC, initialize=lcc_inverter_bus)
    model_any._lcc_indices = lcc_indices
    model_any.pdc_initial = pyo.Param(model_any.LCC, initialize=lcc_power_initial)
    model_any.vdc_rect_initial = pyo.Param(
        model_any.LCC,
        initialize={
            index: value / lcc_vbase[index] for index, value in lcc_vdc_rect_initial.items()
        },
    )
    model_any.vdc_inv_initial = pyo.Param(
        model_any.LCC,
        initialize={
            index: value / lcc_vbase[index] for index, value in lcc_vdc_inv_initial.items()
        },
    )
    model_any.lcc_rdc = pyo.Param(model_any.LCC, initialize=lcc_rdc)
    model_any.lcc_vbase = pyo.Param(model_any.LCC, initialize=lcc_vbase)
    model_any.lcc_rectifier_gain = pyo.Param(model_any.LCC, initialize=lcc_rectifier_gain)
    model_any.lcc_inverter_gain = pyo.Param(model_any.LCC, initialize=lcc_inverter_gain)
    model_any.lcc_rectifier_q_factor = pyo.Param(model_any.LCC, initialize=lcc_rectifier_q_factor)
    model_any.lcc_inverter_q_factor = pyo.Param(model_any.LCC, initialize=lcc_inverter_q_factor)
    model_any.pdc = pyo.Var(
        model_any.LCC,
        initialize=lcc_power_initial,
        bounds=lambda m, index: (0.0, lcc_power_max[index]),
        within=pyo.NonNegativeReals,
    )
    model_any.idc = pyo.Var(
        model_any.LCC,
        initialize=lambda m, index: max(lcc_power_initial[index], 1.0e-6),
        bounds=(1.0e-6, None),
        within=pyo.NonNegativeReals,
    )
    model_any.vdc_rect = pyo.Var(
        model_any.LCC,
        initialize={
            index: value / lcc_vbase[index] for index, value in lcc_vdc_rect_initial.items()
        },
        bounds=(0.5, 1.5),
        within=pyo.PositiveReals,
    )
    model_any.vdc_inv = pyo.Var(
        model_any.LCC,
        initialize={
            index: value / lcc_vbase[index] for index, value in lcc_vdc_inv_initial.items()
        },
        bounds=(0.5, 1.5),
        within=pyo.PositiveReals,
    )
    model_any.alpha = pyo.Var(
        model_any.LCC,
        initialize=lcc_alpha_initial,
        bounds=(math.radians(5.0), math.radians(85.0)),
        within=pyo.NonNegativeReals,
    )
    model_any.gamma = pyo.Var(
        model_any.LCC,
        initialize=lcc_gamma_initial,
        bounds=(math.radians(5.0), math.radians(85.0)),
        within=pyo.NonNegativeReals,
    )
    model_any.qdc_rect = pyo.Var(model_any.LCC, initialize=0.0, within=pyo.Reals)
    model_any.qdc_inv = pyo.Var(model_any.LCC, initialize=0.0, within=pyo.Reals)

    bus_vm_bounds = {}
    bus_va_bounds = {}
    vm_seed = {}
    va_seed = {}
    qg_initial = {}
    qg_lower = {}
    qg_upper = {}
    for bus in case.buses:
        lower, upper = _voltage_bounds(bus, strict_voltage_limits or hard_security)
        bus_vm_bounds[bus.number] = (lower, upper)
        bus_va_bounds[bus.number] = (-ANGLE_BOUND_RAD, ANGLE_BOUND_RAD)
        vm_seed[bus.number] = (
            _bounded_voltage_seed(bus, strict_voltage_limits)
            if not hard_security
            else min(max(1.0, lower + 1.0e-5), upper - 1.0e-5)
        )
        va_seed[bus.number] = 0.0 if hard_security else min(
            max(bus.angle, -ANGLE_BOUND_RAD), ANGLE_BOUND_RAD
        )
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
    if selected_formulation.name in LINEAR_FORMULATIONS:
        for bus in model_any.BUS:
            cast(Any, model_any.vm[bus]).fix(1.0)
    if selected_formulation.name == "ACRPowerModel":
        add_acr_voltage_variables(
            model_any,
            bus_ids=bus_ids,
            vm_seed=vm_seed,
            va_seed=va_seed,
            voltage_bounds=bus_vm_bounds,
        )
    elif selected_formulation.name == "ACTPowerModel":
        buspairs = list({
            (min(branch.from_bus, branch.to_bus), max(branch.from_bus, branch.to_bus))
            for branch in branches
        })
        add_act_voltage_variables(
            model_any,
            bus_ids=bus_ids,
            vm_seed=vm_seed,
            va_seed=va_seed,
            voltage_bounds=bus_vm_bounds,
            buspairs=buspairs,
        )
    elif selected_formulation.name == "IVRPowerModel":
        add_ivr_variables(
            model_any,
            voltage_bounds=bus_vm_bounds,
            vm_seed=vm_seed,
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

    shunt_ids = list(range(len(case.shunt_controls or [])))
    shunt_bus = {}
    shunt_ctrl_bus = {}
    shunt_q_initial = {}
    shunt_q_min = {}
    shunt_q_max = {}
    shunt_vmin = {}
    shunt_vmax = {}
    shunt_is_fixed = {}
    for index, shunt in enumerate(case.shunt_controls or []):
        shunt_bus[index] = shunt.bus
        shunt_ctrl_bus[index] = shunt.controlled_bus
        shunt_initial = shunt.reactive_power / base_mva
        shunt_q_initial[index] = shunt_initial
        shunt_q_min[index] = shunt.minimum_reactive_power / base_mva - shunt_initial
        shunt_q_max[index] = shunt.maximum_reactive_power / base_mva - shunt_initial
        shunt_vmin[index] = shunt.minimum_voltage
        shunt_vmax[index] = shunt.maximum_voltage
        shunt_is_fixed[index] = shunt.fixed or shunt.maximum_voltage <= shunt.minimum_voltage
    model_any.SHUNT = pyo.Set(initialize=shunt_ids, ordered=True)
    model_any.shunt_bus = pyo.Param(model_any.SHUNT, initialize=shunt_bus)
    model_any.shunt_ctrl_bus = pyo.Param(model_any.SHUNT, initialize=shunt_ctrl_bus)
    model_any.shunt_q_initial = pyo.Param(model_any.SHUNT, initialize=shunt_q_initial)
    model_any.shunt_q_min = pyo.Param(model_any.SHUNT, initialize=shunt_q_min)
    model_any.shunt_q_max = pyo.Param(model_any.SHUNT, initialize=shunt_q_max)
    model_any.shunt_vmin = pyo.Param(model_any.SHUNT, initialize=shunt_vmin)
    model_any.shunt_vmax = pyo.Param(model_any.SHUNT, initialize=shunt_vmax)
    model_any.qshunt = pyo.Var(
        model_any.SHUNT,
        initialize={index: 0.0 for index in shunt_ids},
        bounds=lambda m, index: (shunt_q_min[index], shunt_q_max[index]),
        within=pyo.Reals,
    )

    def shunt_voltage_lower_rule(m: Any, index: int):
        if shunt_is_fixed[index] or shunt_vmax[index] <= shunt_vmin[index]:
            return pyo.Constraint.Skip
        return m.vm[int(_value_or_default(m.shunt_ctrl_bus[index]))] >= m.shunt_vmin[index]

    def shunt_voltage_upper_rule(m: Any, index: int):
        if shunt_is_fixed[index] or shunt_vmax[index] <= shunt_vmin[index]:
            return pyo.Constraint.Skip
        return m.vm[int(_value_or_default(m.shunt_ctrl_bus[index]))] <= m.shunt_vmax[index]

    if enforce_shunt_deadbands:
        model_any.shunt_voltage_lower = pyo.Constraint(
            model_any.SHUNT, rule=shunt_voltage_lower_rule
        )
        model_any.shunt_voltage_upper = pyo.Constraint(
            model_any.SHUNT, rule=shunt_voltage_upper_rule
        )

    ltc_ids = [index for index, branch in enumerate(branches) if _is_ltc_branch(index, branch)]
    ltc_bus = {}
    ltc_ctrl_bus = {}
    ltc_tap_initial = {}
    ltc_tap_min = {}
    ltc_tap_max = {}
    ltc_v_target = {}
    for index, branch in enumerate(branches):
        if index not in ltc_ids:
            continue
        ltc_bus[index] = branch.from_bus
        ltc_ctrl_bus[index] = int(branch.controlled_bus or branch.from_bus)
        ltc_tap_initial[index] = branch.tap
        ltc_tap_min[index] = branch.minimum_tap
        ltc_tap_max[index] = branch.maximum_tap
        ltc_v_target[index] = branch.target_voltage
    model_any.LTC = pyo.Set(initialize=ltc_ids, ordered=True)
    model_any.ltc_bus = pyo.Param(model_any.LTC, initialize=ltc_bus)
    model_any.ltc_ctrl_bus = pyo.Param(model_any.LTC, initialize=ltc_ctrl_bus)
    model_any.ltc_tap_initial = pyo.Param(model_any.LTC, initialize=ltc_tap_initial)
    model_any.ltc_tap_min = pyo.Param(model_any.LTC, initialize=ltc_tap_min)
    model_any.ltc_tap_max = pyo.Param(model_any.LTC, initialize=ltc_tap_max)
    model_any.ltc_v_target = pyo.Param(model_any.LTC, initialize=ltc_v_target)
    if optimize_ltc_taps:
        model_any.tap = pyo.Var(
            model_any.LTC,
            initialize=ltc_tap_initial,
            bounds=lambda m, index: (ltc_tap_min[index], ltc_tap_max[index]),
            within=pyo.PositiveReals,
        )
    if optimize_ltc_controls:
        model_any.ltc_residual_pos = pyo.Var(
            model_any.LTC, within=pyo.NonNegativeReals, initialize=0.0
        )
        model_any.ltc_residual_neg = pyo.Var(
            model_any.LTC, within=pyo.NonNegativeReals, initialize=0.0
        )

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
    branch_x = {
        index: branch.reactance if abs(branch.reactance) > TOLERANCE else TOLERANCE
        for index, branch in enumerate(branches)
    }
    branch_phase_shift = {index: branch.phase_shift for index, branch in enumerate(branches)}
    model_any.branch_yff_g = pyo.Param(model_any.BRANCH, initialize=branch_yff_g)
    model_any.branch_yff_b = pyo.Param(model_any.BRANCH, initialize=branch_yff_b)
    model_any.branch_yft_g = pyo.Param(model_any.BRANCH, initialize=branch_yft_g)
    model_any.branch_yft_b = pyo.Param(model_any.BRANCH, initialize=branch_yft_b)
    model_any.branch_ytf_g = pyo.Param(model_any.BRANCH, initialize=branch_ytf_g)
    model_any.branch_ytf_b = pyo.Param(model_any.BRANCH, initialize=branch_ytf_b)
    model_any.branch_ytt_g = pyo.Param(model_any.BRANCH, initialize=branch_ytt_g)
    model_any.branch_ytt_b = pyo.Param(model_any.BRANCH, initialize=branch_ytt_b)
    branch_smax = {
        index: max(abs(branch.rating) / base_mva, TOLERANCE)
        for index, branch in enumerate(branches)
    }
    model_any.branch_smax = pyo.Param(model_any.BRANCH, initialize=branch_smax)
    model_any.pf_from = pyo.Var(model_any.BRANCH, within=pyo.Reals)
    model_any.qf_from = pyo.Var(model_any.BRANCH, within=pyo.Reals)
    model_any.pf_to = pyo.Var(model_any.BRANCH, within=pyo.Reals)
    model_any.qf_to = pyo.Var(model_any.BRANCH, within=pyo.Reals)

    injections: dict[int, list[tuple[int, int, bool]]] = defaultdict(list)
    for index, branch in enumerate(branches):
        injections[branch.from_bus].append((branch.to_bus, index, True))
        injections[branch.to_bus].append((branch.from_bus, index, False))
    svcs_by_bus: dict[int, list[int]] = defaultdict(list)
    for index in svc_ids:
        svcs_by_bus[svc_bus[index]].append(index)
    shunts_by_bus: dict[int, list[int]] = defaultdict(list)
    for index in shunt_ids:
        shunts_by_bus[shunt_bus[index]].append(index)
    ltc_ids_set = set(ltc_ids)

    def _branch_tap(m: Any, branch_index: int):
        if optimize_ltc_taps and branch_index in ltc_ids_set:
            return m.tap[branch_index]
        return branch_tap[branch_index]

    def p_calc(m: Any, bus: int):
        expr = 0.0
        for other, branch_index, from_side in injections.get(bus, []):
            tap = _branch_tap(m, branch_index)
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
            delta = m.va[bus] - m.va[other]
            expr += m.vm[bus] ** 2 * self_g
            expr += (
                m.vm[bus] * m.vm[other] * (mutual_g * pyo.cos(delta) + mutual_b * pyo.sin(delta))
            )
        return expr

    def q_calc(m: Any, bus: int):
        expr = -m.b_shunt[bus] * m.vm[bus] ** 2
        for other, branch_index, from_side in injections.get(bus, []):
            tap = _branch_tap(m, branch_index)
            conductance = branch_g[branch_index]
            susceptance = branch_b[branch_index]
            self_b = branch_b_self[branch_index]
            cos_shift = branch_cos_shift[branch_index]
            sin_shift = branch_sin_shift[branch_index]
            if from_side:
                self_b = self_b / (tap * tap)
                mutual_g = (-conductance * cos_shift + susceptance * sin_shift) / tap
                mutual_b = (-conductance * sin_shift - susceptance * cos_shift) / tap
            else:
                mutual_g = (-conductance * cos_shift - susceptance * sin_shift) / tap
                mutual_b = (conductance * sin_shift - susceptance * cos_shift) / tap
            delta = m.va[bus] - m.va[other]
            expr -= m.vm[bus] ** 2 * self_b
            expr += (
                m.vm[bus] * m.vm[other] * (mutual_g * pyo.sin(delta) - mutual_b * pyo.cos(delta))
            )
        return expr

    if selected_formulation.name == "ACRPowerModel":
        model_any.calculated_p_injection = pyo.Expression(
            model_any.BUS,
            rule=lambda m, bus: p_injection(
                m,
                bus,
                injections,
                branch_g,
                branch_b,
                branch_tap,
                branch_cos_shift,
                branch_sin_shift,
            ),
        )
        model_any.calculated_q_injection = pyo.Expression(
            model_any.BUS,
            rule=lambda m, bus: q_injection(
                m,
                bus,
                injections,
                branch_g,
                branch_b,
                branch_b_self,
                branch_tap,
                branch_cos_shift,
                branch_sin_shift,
            ),
        )
    elif selected_formulation.name == "ACTPowerModel":
        model_any.calculated_p_injection = pyo.Expression(
            model_any.BUS,
            rule=lambda m, bus: act_p_injection(
                m, bus, injections, branch_g, branch_b, branch_tap,
                branch_cos_shift, branch_sin_shift,
            ),
        )
        model_any.calculated_q_injection = pyo.Expression(
            model_any.BUS,
            rule=lambda m, bus: act_q_injection(
                m, bus, injections, branch_g, branch_b, branch_b_self,
                branch_tap, branch_cos_shift, branch_sin_shift,
            ),
        )
    elif selected_formulation.name in LINEAR_FORMULATIONS:
        model_any.calculated_p_injection = pyo.Expression(
            model_any.BUS,
            rule=lambda m, bus: linear_p_injection(m, bus, injections, branch_b),
        )
        model_any.calculated_q_injection = pyo.Expression(
            model_any.BUS, rule=lambda _m, _bus: 0.0
        )
    elif selected_formulation.name == "IVRPowerModel":
        def ivr_injection(m: Any, bus: int, reactive: bool):
            expression = -m.b_shunt[bus] * m.vm[bus] ** 2 if reactive else 0.0
            for other, branch_index, from_side in injections.get(bus, []):
                power = ivr_branch_power(m, branch_index, from_side=from_side)
                expression += power[1 if reactive else 0]
            return expression

        model_any.calculated_p_injection = pyo.Expression(
            model_any.BUS, rule=lambda m, bus: ivr_injection(m, bus, False)
        )
        model_any.calculated_q_injection = pyo.Expression(
            model_any.BUS, rule=lambda m, bus: ivr_injection(m, bus, True)
        )
        add_ivr_branch_equations(
            model_any,
            branches=branches,
            branch_yff_g=branch_yff_g,
            branch_yff_b=branch_yff_b,
            branch_yft_g=branch_yft_g,
            branch_yft_b=branch_yft_b,
            branch_ytf_g=branch_ytf_g,
            branch_ytf_b=branch_ytf_b,
            branch_ytt_g=branch_ytt_g,
            branch_ytt_b=branch_ytt_b,
        )
    else:
        model_any.calculated_p_injection = pyo.Expression(model_any.BUS, rule=p_calc)
        model_any.calculated_q_injection = pyo.Expression(model_any.BUS, rule=q_calc)

    reference_bus = next(
        (bus.number for bus in case.buses if _bus_type_code(bus.kind) == SLACK),
        None,
    )
    for bus in case.buses:
        if _bus_type_code(bus.kind) == SLACK and not hard_security:
            cast(Any, model_any.vm[bus.number]).fix(vm_seed[bus.number])
            cast(Any, model_any.va[bus.number]).fix(va_seed[bus.number])
        elif hard_security and bus.number == reference_bus:
            cast(Any, model_any.va[bus.number]).fix(0.0)
        elif (
            bus.kind == ACBusTypes.PV
            and bus.number not in q_limited_pv_ids
            and not strict_voltage_limits
            and not hard_security
        ):
            cast(Any, model_any.vm[bus.number]).fix(vm_seed[bus.number])

    def p_balance_rule(m: Any, bus: int):
        data = bus_by_id[bus]
        if _bus_type_code(data.kind) == SLACK and not hard_security:
            return pyo.Constraint.Skip
        p_generation = (
            m.pg_security[bus]
            if bus in m.security_generator_ids
            else data.active_generation / base_mva
        )
        p_lcc_delta = sum(
            (lcc_p_rect_initial[index] - (m.pdc[index] + m.lcc_rdc[index] * m.idc[index] ** 2))
            for index in m.LCC
            if lcc_rectifier_bus[index] == bus
        ) + sum(
            (m.pdc[index] - lcc_p_inv_initial[index])
            for index in m.LCC
            if lcc_inverter_bus[index] == bus
        )
        return (
            p_generation - data.active_load / base_mva + p_lcc_delta - m.calculated_p_injection[bus]
            == m.p_slack_pos[bus] - m.p_slack_neg[bus]
        )

    def q_balance_rule(m: Any, bus: int):
        data = bus_by_id[bus]
        if selected_formulation.name in LINEAR_FORMULATIONS:
            return pyo.Constraint.Skip
        if hard_security:
            q_generation = (
                m.qg_security[bus]
                if bus in m.security_generator_ids
                else 0.0
            )
            q_lcc_delta = sum(
                (lcc_q_rect_initial[index] - m.qdc_rect[index])
                for index in m.LCC
                if lcc_rectifier_bus[index] == bus
            ) + sum(
                (lcc_q_inv_initial[index] - m.qdc_inv[index])
                for index in m.LCC
                if lcc_inverter_bus[index] == bus
            )
            q_control = sum(
                m.qsvc[index] for index in svcs_by_bus.get(bus, [])
            ) + sum(
                m.qshunt[index] * m.vm[bus] ** 2
                for index in shunts_by_bus.get(bus, [])
            )
            return (
                q_generation - data.reactive_load / base_mva + q_lcc_delta + q_control
                - m.calculated_q_injection[bus]
                == 0.0
            )
        q_limited_pv = bus in m.QPV
        if _bus_type_code(data.kind) != PQ and not q_limited_pv:
            return pyo.Constraint.Skip
        q_spec = m.q_spec[bus]
        q_lcc_delta = sum(
            (lcc_q_rect_initial[index] - m.qdc_rect[index])
            for index in m.LCC
            if lcc_rectifier_bus[index] == bus
        ) + sum(
            (lcc_q_inv_initial[index] - m.qdc_inv[index])
            for index in m.LCC
            if lcc_inverter_bus[index] == bus
        )
        q_spec = q_spec + q_lcc_delta
        if q_limited_pv:
            q_spec = q_spec + m.qg_qpv[bus]
        for svc_index in svcs_by_bus.get(bus, []):
            q_spec = q_spec + m.qsvc[svc_index]
        for shunt_index in shunts_by_bus.get(bus, []):
            q_spec = q_spec + m.qshunt[shunt_index] * m.vm[bus] ** 2
        return q_spec - m.calculated_q_injection[bus] == m.q_slack_pos[bus] - m.q_slack_neg[bus]

    model_any.active_power_balance = pyo.Constraint(model_any.BUS, rule=p_balance_rule)
    model_any.reactive_power_balance = pyo.Constraint(model_any.BUS, rule=q_balance_rule)

    def branch_p_from_rule(m: Any, index: int):
        branch = branches[index]
        delta = m.va[branch.from_bus] - m.va[branch.to_bus]
        return m.pf_from[index] == (
            m.vm[branch.from_bus] ** 2 * branch_yff_g[index]
            + m.vm[branch.from_bus]
            * m.vm[branch.to_bus]
            * (branch_yft_g[index] * pyo.cos(delta) + branch_yft_b[index] * pyo.sin(delta))
        )

    def branch_q_from_rule(m: Any, index: int):
        branch = branches[index]
        delta = m.va[branch.from_bus] - m.va[branch.to_bus]
        return m.qf_from[index] == (
            -m.vm[branch.from_bus] ** 2 * branch_yff_b[index]
            + m.vm[branch.from_bus]
            * m.vm[branch.to_bus]
            * (branch_yft_g[index] * pyo.sin(delta) - branch_yft_b[index] * pyo.cos(delta))
        )

    def branch_p_to_rule(m: Any, index: int):
        branch = branches[index]
        delta = m.va[branch.to_bus] - m.va[branch.from_bus]
        return m.pf_to[index] == (
            m.vm[branch.to_bus] ** 2 * branch_ytt_g[index]
            + m.vm[branch.to_bus]
            * m.vm[branch.from_bus]
            * (branch_ytf_g[index] * pyo.cos(delta) + branch_ytf_b[index] * pyo.sin(delta))
        )

    def branch_q_to_rule(m: Any, index: int):
        branch = branches[index]
        delta = m.va[branch.to_bus] - m.va[branch.from_bus]
        return m.qf_to[index] == (
            -m.vm[branch.to_bus] ** 2 * branch_ytt_b[index]
            + m.vm[branch.to_bus]
            * m.vm[branch.from_bus]
            * (branch_ytf_g[index] * pyo.sin(delta) - branch_ytf_b[index] * pyo.cos(delta))
        )

    if selected_formulation.name == "ACRPowerModel":
        model_any.branch_p_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.pf_from[index]
            == branch_power(
                m,
                index,
                from_side=True,
                branch_g=branch_g,
                branch_b=branch_b,
                branch_b_self=branch_b_self,
                branch_tap=branch_tap,
                branch_cos_shift=branch_cos_shift,
                branch_sin_shift=branch_sin_shift,
            )[0],
        )
        model_any.branch_q_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.qf_from[index]
            == branch_power(
                m,
                index,
                from_side=True,
                branch_g=branch_g,
                branch_b=branch_b,
                branch_b_self=branch_b_self,
                branch_tap=branch_tap,
                branch_cos_shift=branch_cos_shift,
                branch_sin_shift=branch_sin_shift,
            )[1],
        )
        model_any.branch_p_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.pf_to[index]
            == branch_power(
                m,
                index,
                from_side=False,
                branch_g=branch_g,
                branch_b=branch_b,
                branch_b_self=branch_b_self,
                branch_tap=branch_tap,
                branch_cos_shift=branch_cos_shift,
                branch_sin_shift=branch_sin_shift,
            )[0],
        )
        model_any.branch_q_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.qf_to[index]
            == branch_power(
                m,
                index,
                from_side=False,
                branch_g=branch_g,
                branch_b=branch_b,
                branch_b_self=branch_b_self,
                branch_tap=branch_tap,
                branch_cos_shift=branch_cos_shift,
                branch_sin_shift=branch_sin_shift,
            )[1],
        )
    elif selected_formulation.name == "ACTPowerModel":
        def act_branch_constraint(m: Any, index: int, side: bool, flow: Any, reactive: bool):
            values = act_branch_power(
                m, index, from_side=side, branch_g=branch_g, branch_b=branch_b,
                branch_b_self=branch_b_self, branch_tap=branch_tap,
                branch_cos_shift=branch_cos_shift, branch_sin_shift=branch_sin_shift,
            )
            return flow[index] == values[1 if reactive else 0]

        model_any.branch_p_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: act_branch_constraint(
                m, index, True, m.pf_from, False
            ),
        )
        model_any.branch_q_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: act_branch_constraint(
                m, index, True, m.qf_from, True
            ),
        )
        model_any.branch_p_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: act_branch_constraint(
                m, index, False, m.pf_to, False
            ),
        )
        model_any.branch_q_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: act_branch_constraint(
                m, index, False, m.qf_to, True
            ),
        )
    elif selected_formulation.name in LINEAR_FORMULATIONS:
        transformer_aware = selected_formulation.name == "DCMPPowerModel"
        model_any.branch_p_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.pf_from[index]
            == linear_branch_power(
                m, index, from_side=True, branch_b=branch_b, branch_x=branch_x,
                branch_tap=branch_tap, branch_phase_shift=branch_phase_shift,
                transformer_aware=transformer_aware,
            ),
        )
        model_any.branch_p_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: m.pf_to[index]
            == linear_branch_power(
                m, index, from_side=False, branch_b=branch_b, branch_x=branch_x,
                branch_tap=branch_tap, branch_phase_shift=branch_phase_shift,
                transformer_aware=transformer_aware,
            ),
        )
        model_any.branch_q_from = pyo.Constraint(
            model_any.BRANCH, rule=lambda m, index: m.qf_from[index] == 0.0
        )
        model_any.branch_q_to = pyo.Constraint(
            model_any.BRANCH, rule=lambda m, index: m.qf_to[index] == 0.0
        )
    elif selected_formulation.name == "IVRPowerModel":
        def ivr_branch_constraint(m: Any, index: int, side: bool, reactive: bool):
            values = ivr_branch_power(m, index, from_side=side)
            flow = m.qf_from if reactive and side else (
                m.qf_to if reactive else m.pf_from if side else m.pf_to
            )
            return flow[index] == values[1 if reactive else 0]

        model_any.branch_p_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: ivr_branch_constraint(m, index, True, False),
        )
        model_any.branch_q_from = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: ivr_branch_constraint(m, index, True, True),
        )
        model_any.branch_p_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: ivr_branch_constraint(m, index, False, False),
        )
        model_any.branch_q_to = pyo.Constraint(
            model_any.BRANCH,
            rule=lambda m, index: ivr_branch_constraint(m, index, False, True),
        )
    else:
        model_any.branch_p_from = pyo.Constraint(model_any.BRANCH, rule=branch_p_from_rule)
        model_any.branch_q_from = pyo.Constraint(model_any.BRANCH, rule=branch_q_from_rule)
        model_any.branch_p_to = pyo.Constraint(model_any.BRANCH, rule=branch_p_to_rule)
        model_any.branch_q_to = pyo.Constraint(model_any.BRANCH, rule=branch_q_to_rule)

    def phase_angle_upper_rule(m: Any, index: int):
        branch = branches[index]
        return m.va[branch.from_bus] - m.va[branch.to_bus] <= m.angle_limit

    def phase_angle_lower_rule(m: Any, index: int):
        branch = branches[index]
        return m.va[branch.from_bus] - m.va[branch.to_bus] >= -m.angle_limit

    def thermal_from_rule(m: Any, index: int):
        return m.pf_from[index] ** 2 + m.qf_from[index] ** 2 <= m.branch_smax[index] ** 2

    def thermal_to_rule(m: Any, index: int):
        return m.pf_to[index] ** 2 + m.qf_to[index] ** 2 <= m.branch_smax[index] ** 2

    if objective_function == "voltage_deviation":
        model_any.phase_angle_upper = pyo.Constraint(
            model_any.BRANCH, rule=phase_angle_upper_rule
        )
        model_any.phase_angle_lower = pyo.Constraint(
            model_any.BRANCH, rule=phase_angle_lower_rule
        )
        model_any.thermal_limit_from = pyo.Constraint(model_any.BRANCH, rule=thermal_from_rule)
        model_any.thermal_limit_to = pyo.Constraint(model_any.BRANCH, rule=thermal_to_rule)
        model_any.security_hard_active = pyo.Constraint(
            model_any.BUS,
            rule=lambda m, bus: m.p_slack_pos[bus] + m.p_slack_neg[bus] == 0.0,
        )
        model_any.security_hard_reactive = pyo.Constraint(
            model_any.BUS,
            rule=lambda m, bus: m.q_slack_pos[bus] + m.q_slack_neg[bus] == 0.0,
        )
        model_any.security_hard_voltage = pyo.Constraint(
            model_any.BUS,
            rule=lambda m, bus: m.v_upper_slack[bus] + m.v_lower_slack[bus] == 0.0,
        )
        model_any.security_hard_angle = pyo.Constraint(
            model_any.BUS,
            rule=lambda m, bus: m.a_upper_slack[bus] + m.a_lower_slack[bus] == 0.0,
        )

    def dc_current_rule(m: Any, index: int):
        return m.pdc[index] == m.idc[index] * m.vdc_rect[index]

    def dc_voltage_drop_rule(m: Any, index: int):
        return m.vdc_rect[index] - m.vdc_inv[index] == m.lcc_rdc[index] * m.idc[index]

    def rectifier_voltage_rule(m: Any, index: int):
        lcc = lcc_data[index]
        return m.vdc_rect[index] == (
            m.lcc_rectifier_gain[index]
            * m.vm[lcc.rectifier_bus]
            * pyo.cos(m.alpha[index])
            / max(math.cos(math.radians(lcc.alpha_deg)), 1.0e-6)
        )

    def inverter_voltage_rule(m: Any, index: int):
        lcc = lcc_data[index]
        return m.vdc_inv[index] == (
            m.lcc_inverter_gain[index]
            * m.vm[lcc.inverter_bus]
            * pyo.cos(m.gamma[index])
            / max(math.cos(math.radians(lcc.gamma_deg)), 1.0e-6)
        )

    def rectifier_reactive_rule(m: Any, index: int):
        return (
            m.qdc_rect[index]
            == (m.pdc[index] + m.lcc_rdc[index] * m.idc[index] ** 2)
            * m.lcc_rectifier_q_factor[index]
        )

    def inverter_reactive_rule(m: Any, index: int):
        return m.qdc_inv[index] == m.pdc[index] * m.lcc_inverter_q_factor[index]

    model_any.dc_current_balance = pyo.Constraint(model_any.LCC, rule=dc_current_rule)
    model_any.dc_voltage_drop = pyo.Constraint(model_any.LCC, rule=dc_voltage_drop_rule)
    model_any.rectifier_converter_equation = pyo.Constraint(
        model_any.LCC, rule=rectifier_voltage_rule
    )
    model_any.inverter_converter_equation = pyo.Constraint(
        model_any.LCC, rule=inverter_voltage_rule
    )
    model_any.rectifier_reactive_exchange = pyo.Constraint(
        model_any.LCC, rule=rectifier_reactive_rule
    )
    model_any.inverter_reactive_exchange = pyo.Constraint(
        model_any.LCC, rule=inverter_reactive_rule
    )

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

    def ltc_voltage_rule(m: Any, index: int):
        return (
            m.vm[int(_value_or_default(m.ltc_ctrl_bus[index]))] - m.ltc_v_target[index]
            == m.ltc_residual_pos[index] - m.ltc_residual_neg[index]
        )

    def ltc_residual_tolerance_rule(m: Any, index: int):
        return m.ltc_residual_pos[index] + m.ltc_residual_neg[index] <= m.control_tolerance

    if optimize_ltc_controls:
        model_any.ltc_voltage_control = pyo.Constraint(model_any.LTC, rule=ltc_voltage_rule)
        model_any.ltc_residual_tolerance = pyo.Constraint(
            model_any.LTC, rule=ltc_residual_tolerance_rule
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
        if optimize_ltc_controls:
            ltc_slacks = sum(
                m.ltc_residual_pos[index] ** 2 + m.ltc_residual_neg[index] ** 2 for index in m.LTC
            )
        else:
            ltc_slacks = 0.0
        voltage_limit_slacks = sum(
            m.v_upper_slack[bus] ** 2 + m.v_lower_slack[bus] ** 2 for bus in m.BUS
        )
        voltage_regularization = sum((m.vm[bus] - vm_seed[bus]) ** 2 for bus in m.BUS)
        angle_limit_slacks = sum(
            m.a_upper_slack[bus] ** 2 + m.a_lower_slack[bus] ** 2 for bus in m.BUS
        )
        angle_regularization = sum((m.va[bus] - va_seed[bus]) ** 2 for bus in m.BUS)
        if optimize_ltc_taps:
            ltc_regularization = sum(
                (m.tap[index] - ltc_tap_initial[index]) ** 2 for index in m.LTC
            )
        else:
            ltc_regularization = 0.0
        reactive_generation_regularization = sum(
            (m.qg_qpv[bus] - qg_initial[bus]) ** 2 for bus in m.QPV
        )
        lcc_regularization = sum(
            (m.pdc[index] - lcc_power_initial[index]) ** 2
            + (m.vdc_rect[index] - pyo.value(m.vdc_rect_initial[index])) ** 2
            + (m.vdc_inv[index] - pyo.value(m.vdc_inv_initial[index])) ** 2
            for index in m.LCC
        )
        return (
            power_slacks
            + m.weight_svc * svc_slacks
            + 100.0 * ltc_slacks
            + m.weight_voltage_limits * voltage_limit_slacks
            + m.weight_voltage * voltage_regularization
            + m.weight_angle_limits * angle_limit_slacks
            + m.weight_angle * angle_regularization
            + m.weight_ltc * ltc_regularization
            + reactive_generation_regularization
            + lcc_regularization
        )

    model_any._strict_voltage_limits = strict_voltage_limits
    model_any._formulation = selected_formulation.name

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
    for index, shunt in enumerate(case.shunt_controls or []):
        if shunt_is_fixed[index]:
            cast(Any, model_any.qshunt[index]).fix(0.0)
        else:
            cast(Any, model_any.qshunt[index]).set_value(0.0, skip_validation=True)
    for index in ltc_ids:
        if not optimize_ltc_controls:
            break
        _set_signed_slack(
            model_any.ltc_residual_pos[index],
            model_any.ltc_residual_neg[index],
            vm_seed[ltc_ctrl_bus[index]] - ltc_v_target[index],
        )

    model_any.objective = pyo.Objective(
        expr=sum((cast(Any, model_any.vm[bus]) - 1.0) ** 2 for bus in model_any.BUS)
        + sum(
            (cast(Any, model_any.pg_security[bus]) - security_pg_initial[bus]) ** 2
            for bus in model_any.security_generator_ids
        )
        + sum(
            (cast(Any, model_any.qg_security[bus]) - security_qg_initial[bus]) ** 2
            for bus in model_any.security_generator_ids
        ),
        sense=pyo.minimize,
    )
    model_any._objective_function = objective_function
    return model


def _sync_optimization_control_state(model: pyo.ConcreteModel, case: PowerFlowCase) -> None:
    """Copy solved optimization control variables back into the numerical case."""
    model_any = cast(Any, model)
    buses_by_number = {bus.number: bus for bus in case.buses}
    for index in getattr(model_any, "SHUNT", []):
        if not hasattr(model_any, "qshunt"):
            break
        shunt = (case.shunt_controls or [])[index]
        delta = _value_or_default(model_any.qshunt[index])
        if abs(delta) <= TOLERANCE:
            continue
        buses_by_number[shunt.bus].shunt_susceptance += delta
        shunt.reactive_power += delta * case.base_mva
    for index in getattr(model_any, "LTC", []):
        if not hasattr(model_any, "tap"):
            break
        branch = case.branches[index]
        branch.tap = _value_or_default(model_any.tap[index], branch.tap)
    for index, case_index in enumerate(getattr(model_any, "_lcc_indices", [])):
        lcc = (case.lccs or [])[case_index]
        pdc = _value_or_default(model_any.pdc[index]) * case.base_mva
        idc = _value_or_default(model_any.idc[index])
        q_rect = _value_or_default(model_any.qdc_rect[index]) * case.base_mva
        q_inv = _value_or_default(model_any.qdc_inv[index]) * case.base_mva
        p_rect = (
            _value_or_default(model_any.pdc[index])
            + _value_or_default(model_any.lcc_rdc[index]) * idc * idc
        ) * case.base_mva
        rectifier = buses_by_number[lcc.rectifier_bus]
        inverter = buses_by_number[lcc.inverter_bus]
        rectifier.active_load += p_rect - lcc.p_rectifier_mw
        rectifier.reactive_load += q_rect - lcc.q_rectifier_mvar
        inverter.active_generation += pdc - lcc.p_inverter_mw
        inverter.reactive_load += q_inv - lcc.q_inverter_mvar
        lcc.pdc_mw = pdc
        lcc.p_rectifier_mw = p_rect
        lcc.p_inverter_mw = pdc
        lcc.q_rectifier_mvar = q_rect
        lcc.q_inverter_mvar = q_inv
        lcc.vdc_rectifier_kv = _value_or_default(model_any.vdc_rect[index]) * lcc.vbase_kv
        lcc.vdc_inverter_kv = _value_or_default(model_any.vdc_inv[index]) * lcc.vbase_kv
        lcc.alpha_deg = math.degrees(_value_or_default(model_any.alpha[index]))
        lcc.gamma_deg = math.degrees(_value_or_default(model_any.gamma[index]))


def solution_metrics(model: pyo.ConcreteModel) -> dict[str, float | bool]:
    """Report maximum and aggregate balance residuals from a solved model.

    Residuals are recomputed directly from the power-balance equations rather
    than from the residual slacks, so the report stays meaningful in the
    ``zero_function``/``squared_generation`` modes where the slacks are fixed at
    zero and an infeasible point is exactly the equation violation. Slack buses
    close the system balance by construction and are excluded from the maximum
    residual, mirroring the Newton-Raphson mismatch metric. An SVC whose droop
    residual exceeds the control tolerance has released its droop row: the
    device cannot regulate to its reference at the solved point, either because
    it sits at a reactive capability limit or because the droop row conflicts
    with the reactive balance. Released controls are not convergence violations
    and are counted separately from the maximum residual.
    """
    if isinstance(model, ConicModel):
        solved = model.solution is not None and model.solution.status.upper() in {
            "SOLVED",
            "ALMOST_SOLVED",
        }
        return {
            "converged": solved,
            "max_p": 0.0 if solved else float("inf"),
            "max_q": 0.0 if solved else float("inf"),
            "max_svc": 0.0,
            "aggregate_p": 0.0,
            "aggregate_q": 0.0,
            "released_svc_count": 0,
        }
    model_any = cast(Any, model)
    case = cast(PowerFlowCase, model_any._case)
    bus_by_id = {bus.number: bus for bus in case.buses}
    lcc_data = [(case.lccs or [])[index] for index in getattr(model_any, "_lcc_indices", [])]
    active_tolerance = pyo.value(model_any.active_tolerance)
    reactive_tolerance = pyo.value(model_any.reactive_tolerance)
    control_tolerance = pyo.value(model_any.control_tolerance)
    svcs_by_bus: dict[int, list[int]] = {}
    for index in model_any.SVC:
        svcs_by_bus.setdefault(int(_value_or_default(model_any.svc_bus[index])), []).append(index)
    shunts_by_bus: dict[int, list[int]] = {}
    for index in model_any.SHUNT:
        shunts_by_bus.setdefault(int(_value_or_default(model_any.shunt_bus[index])), []).append(
            index
        )
    slack_buses = [bus.number for bus in case.buses if _bus_type_code(bus.kind) == SLACK]
    active_residual_buses = [bus.number for bus in case.buses if _bus_type_code(bus.kind) != SLACK]
    if getattr(model_any, "_formulation", "") in LINEAR_FORMULATIONS:
        reactive_residual_buses = []
    else:
        reactive_residual_buses = [
            bus.number
            for bus in case.buses
            if _bus_type_code(bus.kind) == PQ or bus.number in model_any.QPV
        ]
    def reactive_residual(bus: int) -> float:
        if getattr(model_any, "_hard_security", False):
            expr = (
                _value_or_default(model_any.qg_security[bus])
                if bus in model_any.security_generator_ids
                else 0.0
            ) - bus_by_id[bus].reactive_load / case.base_mva
        else:
            expr = _value_or_default(model_any.q_spec[bus])
        for index, lcc in enumerate(lcc_data):
            if lcc.rectifier_bus == bus:
                expr += lcc.q_rectifier_mvar / case.base_mva - _value_or_default(
                    model_any.qdc_rect[index]
                )
            elif lcc.inverter_bus == bus:
                expr += lcc.q_inverter_mvar / case.base_mva - _value_or_default(
                    model_any.qdc_inv[index]
                )
        if bus in model_any.QPV and not getattr(model_any, "_hard_security", False):
            expr += _value_or_default(model_any.qg_qpv[bus])
        for index in svcs_by_bus.get(bus, []):
            expr += _value_or_default(model_any.qsvc[index])
        for index in shunts_by_bus.get(bus, []):
            expr += (
                _value_or_default(model_any.qshunt[index])
                * _value_or_default(model_any.vm[bus]) ** 2
            )
        return expr - _value_or_default(model_any.calculated_q_injection[bus])

    def active_specification(bus: BusData | int) -> float:
        bus_id = bus.number if isinstance(bus, BusData) else bus
        generation = (
            _value_or_default(model_any.pg_security[bus_id])
            if bus_id in model_any.security_generator_ids
            else _value_or_default(model_any.p_spec[bus_id])
        )
        if bus_id in model_any.security_generator_ids:
            generation -= bus_by_id[bus_id].active_load / case.base_mva
        return generation

    max_p = 0.0
    max_q = 0.0
    max_svc = 0.0
    max_p_slack = 0.0
    max_q_slack = 0.0
    released_svc_count = 0
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
                active_specification(bus)
                + sum(
                    lcc.p_rectifier_mw / case.base_mva
                    - (
                        _value_or_default(model_any.pdc[index])
                        + _value_or_default(model_any.lcc_rdc[index])
                        * _value_or_default(model_any.idc[index]) ** 2
                    )
                    for index, lcc in enumerate(lcc_data)
                    if lcc.rectifier_bus == bus.number
                )
                + sum(
                    _value_or_default(model_any.pdc[index]) - lcc.p_inverter_mw / case.base_mva
                    for index, lcc in enumerate(lcc_data)
                    if lcc.inverter_bus == bus.number
                )
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
        vm_ctrl = _value_or_default(
            model_any.vm[int(_value_or_default(model_any.svc_ctrl_bus[index]))]
        )
        q_svc = _value_or_default(model_any.qsvc[index])
        droop = vm_ctrl - _value_or_default(model_any.svc_vref[index])
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
        if abs(droop) > control_tolerance + CONVERGENCE_REPORT_EPS:
            released_svc_count += 1
            continue
        max_svc = max(max_svc, abs(droop))
    aggregate_p = sum(
            active_specification(bus)
        + sum(
            lcc.p_rectifier_mw / case.base_mva
            - (
                _value_or_default(model_any.pdc[index])
                + _value_or_default(model_any.lcc_rdc[index])
                * _value_or_default(model_any.idc[index]) ** 2
            )
            for index, lcc in enumerate(lcc_data)
            if lcc.rectifier_bus == bus
        )
        + sum(
            _value_or_default(model_any.pdc[index]) - lcc.p_inverter_mw / case.base_mva
            for index, lcc in enumerate(lcc_data)
            if lcc.inverter_bus == bus
        )
        - _value_or_default(model_any.calculated_p_injection[bus])
        for bus in active_residual_buses
    )
    aggregate_q = sum(reactive_residual(bus) for bus in reactive_residual_buses)
    return {
        "max_p": max_p,
        "max_q": max_q,
        "max_svc": max_svc,
        "max_p_slack": max_p_slack,
        "max_q_slack": max_q_slack,
        "aggregate_p": aggregate_p,
        "aggregate_q": aggregate_q,
        "released_svc_count": released_svc_count,
        "converged": max_p <= active_tolerance + CONVERGENCE_REPORT_EPS
        and max_q <= reactive_tolerance + CONVERGENCE_REPORT_EPS
        and max_svc <= control_tolerance + CONVERGENCE_REPORT_EPS
        and (
            getattr(model_any, "_hard_security", False)
            or abs(aggregate_p) <= active_tolerance + CONVERGENCE_REPORT_EPS
        )
        and (
            getattr(model_any, "_hard_security", False)
            or abs(aggregate_q) <= reactive_tolerance + CONVERGENCE_REPORT_EPS
        ),
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
    model: pyo.ConcreteModel | ConicModel,
    *,
    max_iterations: int = 30,
    max_cpu_time: float = 300.0,
    print_iterations: bool = False,
):
    """Solve the optimization model with Ipopt and return the results and log."""
    if isinstance(model, ConicModel):
        project = getattr(model, "_clarabel_project", None)
        if project is None:
            project = os.environ.get("O_GRID_CLARABEL_PROJECT")
        if project is None:
            project = ClarabelBridge.bundled_project()
        if not project:
            return None, "Clarabel project is not configured", None
        bridge = ClarabelBridge(project)
        if not bridge.available():
            return None, "Clarabel.jl is not available", None
        result = solve_conic_model(model, bridge)
        status = str(result.status).upper()
        termination = (
            TerminationCondition.optimal
            if status in {"SOLVED", "ALMOST_SOLVED"}
            else TerminationCondition.infeasible
        )
        wrapped = SimpleNamespace(
            solver=SimpleNamespace(termination_condition=termination, status=status)
        )
        return wrapped, status, 0
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
      (soft balance and limit constraints with bounded slacks; the SVC droop is
      a soft control with no hard residual cap, so saturated devices release
      their droop row instead of making the model infeasible).
    * ``zero_function`` -- classic AC power flow: the power-balance equations
      hold as hard equalities and the objective is identically zero, so Ipopt
      performs a pure feasibility solve.  SVC/LTC droop residuals stay soft so
      saturated controllers remain feasible.
    * ``squared_generation`` -- exact power balance with reference-bus
      generation redispatched to minimize the sum of squared active
      generation.
    """

    solver_name: ClassVar[str] = "optimization"

    def __init__(
        self,
        system: System | None = None,
        *,
        tolerance: float | None = None,
        max_iterations: int = 30,
        max_cpu_time: float = 300.0,
        max_control_passes: int = 12,
        print_iterations: bool = False,
        strict_voltage_limits: bool = False,
        objective_function: str = "voltage_deviation",
        formulation: str = "ACPPowerModel",
        clarabel_project: str | Path | None = None,
        optimize_ltc_taps: bool = False,
        optimize_ltc_controls: bool = False,
        enforce_shunt_deadbands: bool = False,
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
        self.max_cpu_time = max_cpu_time
        self.objective_function = objective_function
        self.formulation = formulation
        self.clarabel_project = clarabel_project
        self.optimize_ltc_taps = optimize_ltc_taps
        self.optimize_ltc_controls = optimize_ltc_controls
        self.enforce_shunt_deadbands = enforce_shunt_deadbands

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
        reduction = reduce_closed_switches(
            case,
            low_impedance_threshold=settings.low_impedance_threshold,
            reduce_switches=self.formulation not in CONIC_FORMULATIONS,
        )
        numerical_case = reduction.case
        clamp_svc_seed_to_limits(numerical_case)
        _newton_warm_start(numerical_case, settings)

        model_objective = "voltage_deviation"
        model = build_optimization_model(
            numerical_case,
            active_tolerance_pu=max(settings.active_tolerance, TOLERANCE),
            reactive_tolerance_pu=max(settings.reactive_tolerance, TOLERANCE),
            control_tolerance_pu=max(settings.control_tolerance, TOLERANCE),
            qlim_enabled="QLIM" in settings.options,
            strict_voltage_limits=getattr(self, "strict_voltage_limits", False),
            objective_function=model_objective,
            formulation=getattr(self, "formulation", "ACPPowerModel"),
            optimize_ltc_taps=getattr(self, "optimize_ltc_taps", False),
            optimize_ltc_controls=getattr(self, "optimize_ltc_controls", False),
            enforce_shunt_deadbands=getattr(self, "enforce_shunt_deadbands", False),
        )
        if isinstance(model, ConicModel):
            cast(Any, model)._clarabel_project = self.clarabel_project
        results, solver_log, ipopt_iterations = solve_optimization_model(
            model,
            max_iterations=self.max_iterations,
            max_cpu_time=self.max_cpu_time,
            print_iterations=self.print_iterations,
        )
        if results is None:
            logger.error(
                "ACOPF [{}] failed because the selected solver is unavailable: {}",
                self.formulation,
                solver_log,
            )
            return self._failed_run(
                parsed,
                case,
                reduction,
                settings,
                error=solver_log or "Selected solver is not available",
            )

        termination = getattr(getattr(results, "solver", None), "termination_condition", None)
        if (
            isinstance(model, ConicModel)
            and termination
            in {
                TerminationCondition.infeasible,
                TerminationCondition.infeasibleOrUnbounded,
            }
            and len(numerical_case.buses) < len(case.buses)
        ):
            logger.warning(
                "ACOPF [{}] conic reduction was infeasible; retrying without "
                "low-impedance contraction.",
                self.formulation,
            )
            reduction = ReducedPowerFlowCase(
                case,
                np.arange(len(case.buses), dtype=np.int64),
            )
            numerical_case = reduction.case
            clamp_svc_seed_to_limits(numerical_case)
            _newton_warm_start(numerical_case, settings)
            model = build_optimization_model(
                numerical_case,
                active_tolerance_pu=max(settings.active_tolerance, TOLERANCE),
                reactive_tolerance_pu=max(settings.reactive_tolerance, TOLERANCE),
                control_tolerance_pu=max(settings.control_tolerance, TOLERANCE),
                qlim_enabled="QLIM" in settings.options,
                strict_voltage_limits=getattr(self, "strict_voltage_limits", False),
                objective_function=model_objective,
                formulation=getattr(self, "formulation", "ACPPowerModel"),
                optimize_ltc_taps=getattr(self, "optimize_ltc_taps", False),
                optimize_ltc_controls=getattr(self, "optimize_ltc_controls", False),
                enforce_shunt_deadbands=getattr(self, "enforce_shunt_deadbands", False),
            )
            if isinstance(model, ConicModel):
                cast(Any, model)._clarabel_project = self.clarabel_project
            results, retry_log, ipopt_iterations = solve_optimization_model(
                model,
                max_iterations=self.max_iterations,
                max_cpu_time=self.max_cpu_time,
                print_iterations=self.print_iterations,
            )
            solver_log = f"{solver_log}\n{retry_log}" if retry_log else solver_log
            termination = getattr(getattr(results, "solver", None), "termination_condition", None)
        metrics = solution_metrics(cast(pyo.ConcreteModel, model))
        failed_terminations = {
            TerminationCondition.infeasible,
            TerminationCondition.infeasibleOrUnbounded,
            TerminationCondition.unbounded,
            TerminationCondition.error,
        }
        converged = metrics["converged"] and termination not in failed_terminations
        diverged = termination in {
            TerminationCondition.infeasible,
            TerminationCondition.infeasibleOrUnbounded,
            TerminationCondition.unbounded,
            TerminationCondition.error,
        }
        iterations = (
            model.solution.iterations
            if isinstance(model, ConicModel) and model.solution is not None
            else int(ipopt_iterations or 0)
        )
        max_mismatch = max(metrics["max_p"], metrics["max_q"], metrics["max_svc"])

        vm, va = _solved_voltage(model)
        reduced_voltage = np.array(
            [vm[bus.number] * np.exp(1j * va[bus.number]) for bus in numerical_case.buses],
            dtype=np.complex128,
        )
        _sync_optimization_control_state(cast(pyo.ConcreteModel, model), numerical_case)
        refresh_lcc_reporting_state(numerical_case, reduced_voltage)
        reduction.sync_control_state(case)
        expanded_voltage = reduction.expand_voltage(reduced_voltage)
        result_ybus = build_ybus(case)
        expanded_buses = calculate_bus_results(case, result_ybus, expanded_voltage)
        expanded_branches = calculate_branch_results(case, expanded_voltage)
        security_tolerance = max(
            DISPLAY_TOLERANCE,
            settings.active_tolerance,
            settings.reactive_tolerance,
        )
        security_ok = all(
            bus.minimum_voltage - security_tolerance
            <= bus_result.voltage_pu
            <= bus.maximum_voltage + security_tolerance
            for bus, bus_result in zip(case.buses, expanded_buses)
        ) and all(
            branch_result.loading_percent <= 100.0 + security_tolerance
            for branch_result in expanded_branches
        )
        if self.solver_name == "acopf" and not isinstance(model, ConicModel):
            converged = converged and security_ok
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
                    iteration=index,
                    max_dp=metrics["max_p"],
                    max_dq=metrics["max_q"],
                    max_control_residual=metrics["max_svc"],
                    max_residual=max_mismatch,
                    max_step=0.0,
                )
                for index in range(iterations + 1)
            ],
            buses=expanded_buses,
            branches=expanded_branches,
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
        solver_label = f"ACOPF [{self.formulation}]"
        if converged:
            logger.success(
                "{} converged in {} iteration(s); max mismatch {:.4e} pu.",
                solver_label,
                iterations,
                max_mismatch,
            )
        else:
            logger.error(
                "{} is {} after {} iteration(s); max mismatch {:.4e} pu.",
                solver_label,
                _optimization_failure_state(termination),
                iterations,
                max_mismatch,
            )
        report = summarize_solution(cast(pyo.ConcreteModel, model))
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
            "ACOPF [{}] did not produce a solution: {}.",
            self.formulation,
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
    model: pyo.ConcreteModel | ConicModel,
) -> tuple[dict[int, float], dict[int, float]]:
    if isinstance(model, ConicModel) and model.vm is not None and model.va is not None:
        return model.vm, model.va
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
    formulation = getattr(
        model_any, "formulation", getattr(model_any, "_formulation", "ACPPowerModel")
    )
    lines = [
        f"Optimization power-flow summary for {len(case.buses)} buses, "
        f"{len(case.branches)} branches",
        f"  Formulation: {formulation}",
        f"  Objective function: {getattr(model_any, '_objective_function', 'minimize_residuals')}",
        f"  Converged: {metrics['converged']}",
        f"  Max P residual: {metrics['max_p']:.6e} pu",
        f"  Max Q residual: {metrics['max_q']:.6e} pu",
        f"  Max SVC residual: {metrics['max_svc']:.6e} pu",
        f"  Released SVC controls: {metrics['released_svc_count']}",
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


class ACOptimalPowerFlow(OptimizationACPowerFlow):
    """Strict ACOPF that minimizes voltage deviation when costs are absent."""

    solver_name = "acopf"

    def __new__(
        cls,
        system=None,
        *,
        objective_function: str = "voltage_deviation",
        formulation: str = "ACPPowerModel",
        clarabel_project: str | Path | None = None,
        **kwargs: Any,
    ):
        if objective_function != "voltage_deviation":
            raise ValueError(
                "ACOptimalPowerFlow only supports objective_function='voltage_deviation'"
            )
        return super().__new__(
            cls,
            system=system,
            objective_function="voltage_deviation",
            **kwargs,
        )

    def __init__(
        self,
        *args: Any,
        objective_function: str = "voltage_deviation",
        formulation: str = "ACPPowerModel",
        **kwargs: Any,
    ) -> None:
        if objective_function != "voltage_deviation":
            raise ValueError(
                "ACOptimalPowerFlow only supports objective_function='voltage_deviation'"
            )
        selected_formulation = resolve_formulation(formulation)
        if not selected_formulation.implemented:
            raise NotImplementedError(
                f"ACOPF formulation {selected_formulation.name!r} is registered but not implemented"
            )
        kwargs["objective_function"] = "voltage_deviation"
        kwargs["formulation"] = selected_formulation.name
        super().__init__(*args, **kwargs)
