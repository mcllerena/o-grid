"""In-process orchestration for pure-Python AC power-flow solvers."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Self

from infrasys import System
from loguru import logger

from o_grid.acpf.fast_decoupled import solve_fast_decoupled
from o_grid.acpf.models import build_component_results, build_power_flow_case
from o_grid.acpf.newton_raphson import solve_newton_raphson
from o_grid.acpf.reporting import format_power_flow_report
from o_grid.acpf.results import ACPowerFlowResult, PowerFlowRun, apply_power_flow_result
from o_grid.acpf.utils import (
    assign_island_reference_buses,
    build_ybus,
    calculate_branch_results,
    calculate_bus_results,
)
from o_grid.parser import AnaredeInfrasysParser, ParsedAnaredeSystem


class PowerFlowSolver:
    """Base interface for an in-process Python AC power-flow implementation."""

    solver_name: ClassVar[str]

    def __new__(
        cls,
        system: System | None = None,
        *,
        tolerance: float = 1e-6,
        max_iterations: int = 50,
        print_iterations: bool = False,
    ) -> Self | System:
        instance = super().__new__(cls)
        if system is None:
            return instance
        instance.tolerance = tolerance
        instance.max_iterations = max_iterations
        instance.print_iterations = print_iterations
        return instance.run(system).system

    def __init__(
        self,
        system: System | None = None,
        *,
        tolerance: float = 1e-6,
        max_iterations: int = 50,
        print_iterations: bool = False,
    ) -> None:
        del system
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.print_iterations = print_iterations

    def run(
        self,
        pwf_path: str | Path | System | ParsedAnaredeSystem,
        *,
        system_name: str | None = None,
    ) -> PowerFlowRun:
        """Solve a PWF path or parsed infrasys system and attach its solved values."""
        if isinstance(pwf_path, ParsedAnaredeSystem):
            parsed = pwf_path
        elif isinstance(pwf_path, System):
            parsed = ParsedAnaredeSystem.from_system(pwf_path)
        else:
            source = Path(pwf_path).resolve()
            parser = AnaredeInfrasysParser(system_name=system_name or source.stem)
            parsed = parser.parse(source)

        case = build_power_flow_case(parsed)
        ybus = build_ybus(case)
        assign_island_reference_buses(case, ybus)
        solve = (
            solve_newton_raphson if self.solver_name == "newton-raphson" else solve_fast_decoupled
        )
        solution = solve(
            case,
            ybus,
            tolerance=self.tolerance,
            max_iterations=self.max_iterations,
        )
        result = ACPowerFlowResult(
            solver=self.solver_name,
            converged=solution.converged,
            diverged=solution.diverged,
            iterations=solution.iterations,
            max_mismatch=solution.max_mismatch,
            base_mva=case.base_mva,
            iteration_trace=solution.trace,
            buses=calculate_bus_results(case, ybus, solution.voltage),
            branches=calculate_branch_results(case, solution.voltage),
        )
        apply_power_flow_result(parsed, result)
        component_results = build_component_results(parsed, case, result, tolerance=self.tolerance)
        set_results = getattr(parsed.system, "set_power_flow_results", None)
        if callable(set_results):
            set_results(component_results)
        report = format_power_flow_report(
            result,
            print_iterations=self.print_iterations,
        )
        if report:
            print(report)
        if result.converged:
            logger.success(
                "{} power flow converged in {} iteration(s); max mismatch {:.4e} pu.",
                self.solver_name,
                result.iterations,
                result.max_mismatch or 0.0,
            )
        else:
            logger.error(
                "{} power flow {} after {} iteration(s); max mismatch {:.4e} pu.",
                self.solver_name,
                "diverged" if result.diverged else "did not converge",
                result.iterations,
                result.max_mismatch or 0.0,
            )
        return PowerFlowRun(parsed=parsed, result=result, stdout=report)


class NewtonRaphsonPowerFlow(PowerFlowSolver):
    """Sparse full Newton-Raphson AC power-flow solver."""

    solver_name = "newton-raphson"


class FastDecoupledPowerFlow(PowerFlowSolver):
    """Sparse fast-decoupled AC power-flow solver."""

    solver_name = "fast-decoupled"
