"""HiGHS-backed linear DC optimal power-flow solver."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from infrasys import System
from loguru import logger
from scipy.optimize import linprog

from o_grid.acpf.models import build_component_results, build_power_flow_case
from o_grid.acpf.results import (
    ACPowerFlowResult,
    BranchPowerFlowResult,
    BusPowerFlowResult,
    IterationPowerFlowResult,
    PowerFlowRun,
    apply_power_flow_result,
)
from o_grid.acpf.utils import calculate_branch_results
from o_grid.dcpf.solver import _as_parsed_system
from o_grid.statics.pwf_parser import ParsedAnaredeSystem
from o_grid.units import get_magnitude

PARAMETER_MODES = ("cold_start", "hot_start", "dcpf", "optimal")
_PARAMETER_MODE_ALIASES = {
    "cold": "cold_start",
    "cold-start": "cold_start",
    "hot": "hot_start",
    "hot-start": "hot_start",
    "optimized_dcpf": "dcpf",
    "dc_opf_optimal": "optimal",
}


@dataclass(slots=True)
class DCOPFParameters:
    """Coefficient and bias parameters in the paper's DC-OPF formulation."""

    b: dict[tuple[int, int, int], float]
    gamma: dict[int, float]
    rho: dict[tuple[int, int, int], float]


class DCOptimalPowerFlow:
    """Solve a linear DC-OPF with SciPy's open-source HiGHS backend.

    ``param_opt`` selects the parameterization described in Taheri and Molzahn:
    ``cold_start``, ``hot_start``, ``dcpf``, or ``optimal``. The optimal mode
    requires parameters produced by an offline training workflow and can be
    supplied through ``parameters``.
    """

    solver_name = "dcopf"

    def __init__(
        self,
        system: System | None = None,
        *,
        param_opt: str = "cold_start",
        parameters: DCOPFParameters | None = None,
        generator_costs: Mapping[int, tuple[float, float, float]] | None = None,
        enforce_branch_limits: bool = True,
    ) -> None:
        param_opt = _PARAMETER_MODE_ALIASES.get(param_opt, param_opt)
        if param_opt not in PARAMETER_MODES:
            raise ValueError(f"param_opt must be one of {PARAMETER_MODES}")
        self.param_opt = param_opt
        self.parameters = parameters
        self.generator_costs = generator_costs or {}
        self.enforce_branch_limits = enforce_branch_limits
        self._system = system

    def run(
        self,
        source: str | Path | System | ParsedAnaredeSystem | None = None,
        *,
        system_name: str | None = None,
    ) -> PowerFlowRun:
        source = source or self._system
        if source is None:
            raise ValueError("DCOPF.run requires a source or a system passed to the constructor")
        parsed = _as_parsed_system(source, system_name)
        case = build_power_flow_case(parsed)
        parameters = self._select_parameters(case, parsed)
        buses = {bus.number: index for index, bus in enumerate(case.buses)}
        generators = _build_generators(parsed, case)
        if not generators:
            raise ValueError("DCOPF requires at least one active-power generator")

        generator_count = len(generators)
        bus_count = len(case.buses)
        theta_offset = generator_count
        variable_count = generator_count + bus_count
        objective = np.zeros(variable_count)
        bounds: list[tuple[float, float]] = []
        for index, generator in enumerate(generators):
            cost = self.generator_costs.get(generator[0], (0.0, 1.0, 0.0))
            objective[index] = cost[1] + 2.0 * cost[0] * generator[3]
            bounds.append((generator[1] / case.base_mva, generator[2] / case.base_mva))
        reference = set(case.slack_indices.tolist())
        for index in range(bus_count):
            angle = case.buses[index].angle
            bounds.append((angle, angle) if index in reference else (-math.pi, math.pi))

        equality_rows: list[np.ndarray] = []
        equality_rhs: list[float] = []
        for bus_number, bus_index in buses.items():
            row = np.zeros(variable_count)
            for generator_index, generator in enumerate(generators):
                if generator[0] == bus_number:
                    row[generator_index] += 1.0
            for branch_index, branch in enumerate(case.branches):
                coefficient = parameters.b[_branch_key(branch)]
                if branch.from_bus == bus_number:
                    row[theta_offset + bus_index] -= coefficient
                    row[theta_offset + buses[branch.to_bus]] += coefficient
                elif branch.to_bus == bus_number:
                    row[theta_offset + bus_index] -= coefficient
                    row[theta_offset + buses[branch.from_bus]] += coefficient
            equality_rows.append(row)
            equality_rhs.append(
                (case.buses[bus_index].active_load / case.base_mva)
                + parameters.gamma.get(bus_number, 0.0)
                + _net_rho(case, parameters, bus_number)
            )

        upper_rows: list[np.ndarray] = []
        upper_rhs: list[float] = []
        for branch in case.branches:
            row = np.zeros(variable_count)
            coefficient = parameters.b[_branch_key(branch)]
            row[theta_offset + buses[branch.from_bus]] = coefficient
            row[theta_offset + buses[branch.to_bus]] = -coefficient
            limit = branch.rating / case.base_mva if branch.rating > 0.0 else np.inf
            flow_bias = parameters.rho[_branch_key(branch)]
            if self.enforce_branch_limits and np.isfinite(limit):
                upper_rows.extend((row, -row))
                upper_rhs.extend((limit - flow_bias, limit + flow_bias))

        result = linprog(
            objective,
            A_ub=np.array(upper_rows) if upper_rows else None,
            b_ub=np.array(upper_rhs) if upper_rhs else None,
            A_eq=np.array(equality_rows),
            b_eq=np.array(equality_rhs),
            bounds=bounds,
            method="highs",
        )
        if not result.success:
            logger.error("DC-OPF did not converge: {}", result.message)
            if self.enforce_branch_limits and "infeasible" in result.message.lower():
                logger.error(
                    "Check generator and branch ratings, or set enforce_branch_limits=False "
                    "to diagnose the unconstrained dispatch."
                )
            raise RuntimeError(f"HiGHS DC-OPF failed: {result.message}")

        angles = np.asarray(result.x[theta_offset:], dtype=float)
        branch_results = _branch_results(case, angles, parameters)
        generation = np.zeros(bus_count)
        for index, generator in enumerate(generators):
            generation[buses[generator[0]]] += result.x[index] * case.base_mva
        injections = np.array(
            [generation[index] - bus.active_load for index, bus in enumerate(case.buses)],
            dtype=float,
        ) / case.base_mva
        bus_results = [
            BusPowerFlowResult(
                id=bus.number,
                name=bus.name,
                voltage_pu=1.0,
                angle_rad=float(angles[index]),
                active_injection_pu=float(injections[index]),
                reactive_injection_pu=0.0,
            )
            for index, bus in enumerate(case.buses)
        ]
        result_model = ACPowerFlowResult(
            solver=self.solver_name,
            converged=True,
            diverged=False,
            iterations=1,
            max_mismatch=float(np.max(np.abs(np.array(equality_rows) @ result.x - equality_rhs))),
            base_mva=case.base_mva,
            iteration_trace=[IterationPowerFlowResult(
                iteration=1, max_dp=0.0, max_dq=0.0, max_control_residual=0.0,
                max_residual=0.0, max_step=0.0,
            )],
            buses=bus_results,
            branches=branch_results,
        )
        apply_power_flow_result(parsed, result_model)
        component_results = build_component_results(parsed, case, result_model)
        setter = getattr(parsed.system, "set_power_flow_results", None)
        if callable(setter):
            setter(component_results)
        logger.success(
            "DC-OPF ({}) converged with HiGHS in {} iteration(s); objective {:.6g}.",
            self.param_opt, result_model.iterations, float(result.fun),
        )
        return PowerFlowRun(parsed=parsed, result=result_model, stdout="")

    def _select_parameters(self, case, parsed) -> DCOPFParameters:
        if self.param_opt == "optimal":
            if self.parameters is None:
                raise ValueError("param_opt='optimal' requires trained parameters")
            return self.parameters
        cold = _cold_parameters(case)
        if self.param_opt == "cold_start":
            return cold
        if self.param_opt == "dcpf":
            return _dcpf_parameters(case)
        return _hot_parameters(case, cold)


def _build_generators(parsed, case) -> list[tuple[int, float, float, float]]:
    generators = []
    covered_buses: set[int] = set()
    for component in parsed.components_by_block.get("DGER", []):
        number = _number(getattr(component, "number", None))
        if number not in case.bus_index:
            continue
        minimum = _magnitude(getattr(component, "min_active_generation", None), 0.0)
        maximum = _magnitude(getattr(component, "max_active_generation", None), 99999.0)
        initial = _magnitude(getattr(component, "active_generation", None), minimum)
        maximum = max(maximum, initial)
        generators.append((number, minimum, maximum, initial))
        covered_buses.add(number)
    for bus in case.buses:
        if bus.number not in covered_buses and bus.active_generation > 0.0:
            generators.append((bus.number, 0.0, bus.active_generation, bus.active_generation))
    return generators


def _cold_parameters(case) -> DCOPFParameters:
    b, rho = {}, {}
    for branch in case.branches:
        coefficient = _cold_b(branch)
        key = _branch_key(branch)
        b[key] = coefficient
        rho[key] = -coefficient * branch.phase_shift
    return DCOPFParameters(b=b, gamma={bus.number: 0.0 for bus in case.buses}, rho=rho)


def _dcpf_parameters(case) -> DCOPFParameters:
    parameters = _cold_parameters(case)
    for branch in case.branches:
        parameters.b[_branch_key(branch)] = 1.0 / (branch.reactance * branch.tap)
    return parameters


def _hot_parameters(case, cold) -> DCOPFParameters:
    parameters = DCOPFParameters(dict(cold.b), dict(cold.gamma), dict(cold.rho))
    nominal = calculate_branch_results(case, case.initial_voltage)
    for branch, flow in zip(case.branches, nominal, strict=True):
        key = _branch_key(branch)
        delta = case.buses[case.bus_index[branch.from_bus]].angle - case.buses[
            case.bus_index[branch.to_bus]
        ].angle
        if abs(delta) > 1e-10:
            parameters.b[key] = flow.active_from_mw / case.base_mva / delta
        parameters.rho[key] = flow.active_from_mw / case.base_mva - parameters.b[key] * delta
    net = np.zeros(len(case.buses))
    for flow in nominal:
        net[case.bus_index[flow.from_bus]] += flow.active_from_mw / case.base_mva
        net[case.bus_index[flow.to_bus]] += flow.active_to_mw / case.base_mva
    for index, bus in enumerate(case.buses):
        parameters.gamma[bus.number] = (
            (bus.active_generation - bus.active_load) / case.base_mva - net[index]
        )
    return parameters


def _branch_results(case, angles, parameters):
    results = []
    for branch in case.branches:
        flow = parameters.b[_branch_key(branch)] * (
            angles[case.bus_index[branch.from_bus]] - angles[case.bus_index[branch.to_bus]]
        ) + parameters.rho[_branch_key(branch)]
        flow_mw = flow * case.base_mva
        loading = abs(flow_mw) / branch.rating * 100.0 if branch.rating > 0 else 0.0
        results.append(BranchPowerFlowResult(
            from_bus=branch.from_bus, to_bus=branch.to_bus, circuit=branch.circuit,
            active_from_mw=float(flow_mw), reactive_from_mvar=0.0,
            active_to_mw=float(-flow_mw), reactive_to_mvar=0.0,
            loading_percent=float(loading), active_loss_mw=0.0, reactive_loss_mvar=0.0,
        ))
    return results


def _net_rho(case, parameters, bus_number):
    total = 0.0
    for branch in case.branches:
        rho = parameters.rho[_branch_key(branch)]
        if branch.from_bus == bus_number:
            total += rho
        elif branch.to_bus == bus_number:
            total -= rho
    return total


def _cold_b(branch):
    if abs(branch.reactance) < 1e-12:
        raise ValueError(f"Branch {branch.from_bus}-{branch.to_bus} has zero reactance")
    return branch.reactance / (branch.resistance**2 + branch.reactance**2) / branch.tap


def _branch_key(branch):
    return (branch.from_bus, branch.to_bus, branch.circuit)


def _number(value):
    if value in (None, ""):
        return 0
    value = getattr(value, "number", value)
    return int(float(str(value)))


def _magnitude(value, default=0.0):
    return default if value is None else float(get_magnitude(value))