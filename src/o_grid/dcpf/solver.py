"""Linear DC power-flow solver with optional lossy branch reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Self

import numpy as np
from infrasys import System
from scipy.sparse import csc_matrix, lil_matrix
from scipy.sparse.linalg import spsolve

from o_grid.acpf.models import build_component_results, build_power_flow_case
from o_grid.acpf.results import (
    ACPowerFlowResult,
    BranchPowerFlowResult,
    BusPowerFlowResult,
    IterationPowerFlowResult,
    PowerFlowRun,
    apply_power_flow_result,
)
from o_grid.acpf.utils import assign_island_reference_buses, build_ybus, calculate_branch_results
from o_grid.statics.ntw_parser import NtwFileParser
from o_grid.statics.pwf_parser import AnaredeInfrasysParser, ParsedAnaredeSystem


class DCPowerFlow:
    """Solve the active-power DC power-flow approximation.

    ``lossy_flows=False`` follows the classical DC model. With ``lossy_flows=True``,
    terminal flows and branch losses are calculated from the AC branch admittances
    at unit voltage magnitude, matching the PowerFlows.jl option.
    """

    solver_name = "dc"

    def __new__(
        cls,
        system: System | None = None,
        *,
        lossy_flows: bool = False,
        tolerance: float = 1e-8,
    ) -> Self | System:
        instance = super().__new__(cls)
        if system is None:
            return instance
        instance.lossy_flows = lossy_flows
        instance.tolerance = tolerance
        return instance.run(system).system

    def __init__(
        self,
        system: System | None = None,
        *,
        lossy_flows: bool = False,
        tolerance: float = 1e-8,
    ) -> None:
        del system
        self.lossy_flows = lossy_flows
        self.tolerance = tolerance

    def run(
        self,
        source: str | Path | System | ParsedAnaredeSystem,
        *,
        system_name: str | None = None,
    ) -> PowerFlowRun:
        """Solve a path, parsed system, or infrasys system and attach its results."""
        parsed = _as_parsed_system(source, system_name)
        case = build_power_flow_case(parsed)
        ybus = build_ybus(case)
        assign_island_reference_buses(case, ybus)
        voltage = _solve_angles(case)
        voltage_complex = np.exp(1j * voltage)
        branches = (
            calculate_branch_results(case, voltage_complex)
            if self.lossy_flows
            else _calculate_lossless_branch_results(case, voltage)
        )
        injections = case.specified_power.copy()
        branch_injections = _branch_net_injections(case, branches)
        injections[case.slack_indices] = branch_injections[case.slack_indices]
        bus_results = _calculate_bus_results(case, voltage, injections)
        mismatch = _maximum_mismatch(case, injections, branches)
        trace = [
            IterationPowerFlowResult(
                iteration=0,
                max_dp=mismatch,
                max_dq=0.0,
                max_control_residual=0.0,
                max_residual=mismatch,
                max_step=0.0,
            )
        ]
        result = ACPowerFlowResult(
            solver=self.solver_name,
            converged=True,
            diverged=False,
            iterations=0,
            max_mismatch=mismatch,
            base_mva=case.base_mva,
            iteration_trace=trace,
            buses=bus_results,
            branches=branches,
        )
        apply_power_flow_result(parsed, result)
        component_results = build_component_results(parsed, case, result, tolerance=self.tolerance)
        set_results = getattr(parsed.system, "set_power_flow_results", None)
        if callable(set_results):
            set_results(component_results)
        return PowerFlowRun(parsed=parsed, result=result, stdout="")


def _as_parsed_system(
    source: str | Path | System | ParsedAnaredeSystem,
    system_name: str | None,
) -> ParsedAnaredeSystem:
    if isinstance(source, ParsedAnaredeSystem):
        return source
    if isinstance(source, System):
        return ParsedAnaredeSystem.from_system(source)
    path = Path(source).resolve()
    if path.suffix.lower() == ".ntw":
        system = NtwFileParser(path, system_name=system_name or path.stem).system
        return ParsedAnaredeSystem.from_system(system)
    return AnaredeInfrasysParser(system_name=system_name or path.stem).parse(path)


def _solve_angles(case) -> np.ndarray:
    reference = case.slack_indices
    if reference.size == 0:
        raise ValueError("The infrasys system contains no reference bus")
    susceptance = _build_dc_matrix(case)
    non_reference = np.array(
        [index for index in range(len(case.buses)) if index not in set(reference)], dtype=np.int64
    )
    angles = np.zeros(len(case.buses), dtype=float)
    angles[reference] = np.array([case.buses[index].angle for index in reference])
    if non_reference.size:
        rhs = case.specified_power.real + _phase_shift_injections(case)
        rhs = rhs[non_reference]
        rhs -= susceptance[non_reference, :][:, reference] @ angles[reference]
        angles[non_reference] = np.asarray(
            spsolve(susceptance[non_reference, :][:, non_reference], rhs), dtype=float
        )
    return angles


def _build_dc_matrix(case) -> csc_matrix:
    matrix = lil_matrix((len(case.buses), len(case.buses)), dtype=float)
    indices = case.bus_index
    for branch in case.branches:
        if abs(branch.reactance) < 1e-12:
            raise ValueError(f"Branch {branch.from_bus}-{branch.to_bus} has zero reactance")
        from_index = indices[branch.from_bus]
        to_index = indices[branch.to_bus]
        susceptance = 1.0 / (branch.reactance * branch.tap)
        matrix[from_index, from_index] += susceptance
        matrix[to_index, to_index] += susceptance
        matrix[from_index, to_index] -= susceptance
        matrix[to_index, from_index] -= susceptance
    return matrix.tocsc()


def _phase_shift_injections(case) -> np.ndarray:
    injections = np.zeros(len(case.buses), dtype=float)
    indices = case.bus_index
    for branch in case.branches:
        susceptance = 1.0 / (branch.reactance * branch.tap)
        shift = susceptance * branch.phase_shift
        injections[indices[branch.from_bus]] += shift
        injections[indices[branch.to_bus]] -= shift
    return injections


def _calculate_bus_results(
    case, angles: np.ndarray, injections: np.ndarray
) -> list[BusPowerFlowResult]:
    return [
        BusPowerFlowResult(
            id=bus.number,
            name=bus.name,
            voltage_pu=1.0,
            angle_rad=float(angles[index]),
            active_injection_pu=float(injections[index].real),
            reactive_injection_pu=0.0,
        )
        for index, bus in enumerate(case.buses)
    ]


def _calculate_lossless_branch_results(case, angles: np.ndarray) -> list[BranchPowerFlowResult]:
    results = []
    for branch in case.branches:
        from_angle = angles[case.bus_index[branch.from_bus]]
        to_angle = angles[case.bus_index[branch.to_bus]]
        if abs(branch.reactance) < 1e-12:
            raise ValueError(f"Branch {branch.from_bus}-{branch.to_bus} has zero reactance")
        active_from = (from_angle - to_angle - branch.phase_shift) / branch.reactance
        active_from *= case.base_mva / branch.tap
        maximum_flow = abs(active_from)
        loading = 100.0 * maximum_flow / branch.rating if branch.rating > 0.0 else 0.0
        results.append(
            BranchPowerFlowResult(
                from_bus=branch.from_bus,
                to_bus=branch.to_bus,
                circuit=branch.circuit,
                active_from_mw=float(active_from),
                reactive_from_mvar=0.0,
                active_to_mw=float(-active_from),
                reactive_to_mvar=0.0,
                loading_percent=float(loading),
                active_loss_mw=0.0,
                reactive_loss_mvar=0.0,
            )
        )
    return results


def _maximum_mismatch(case, injections: np.ndarray, branches: list[BranchPowerFlowResult]) -> float:
    net_flow = _branch_net_injections(case, branches)
    return float(np.max(np.abs(injections.real - net_flow))) if net_flow.size else 0.0


def _branch_net_injections(case, branches: list[BranchPowerFlowResult]) -> np.ndarray:
    net_flow = np.zeros(len(case.buses), dtype=float)
    indices = case.bus_index
    for branch in branches:
        net_flow[indices[branch.from_bus]] += branch.active_from_mw / case.base_mva
        net_flow[indices[branch.to_bus]] += branch.active_to_mw / case.base_mva
    return net_flow
