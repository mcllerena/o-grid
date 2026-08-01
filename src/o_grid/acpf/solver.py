"""In-process orchestration for pure-Python AC power-flow solvers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import ClassVar, Self

from infrasys import System
from loguru import logger

from o_grid.acpf.controls import apply_bus_limit_controls
from o_grid.acpf.fast_decoupled import solve_fast_decoupled
from o_grid.acpf.models import (
    build_component_results,
    build_power_flow_case,
    build_power_flow_settings,
    reduce_closed_switches,
)
from o_grid.acpf.models.lcc import refresh_lcc_reporting_state, update_lcc_from_dc_solution
from o_grid.acpf.models.ltc import adjust_ltc_taps
from o_grid.acpf.models.shunt import adjust_switched_shunts
from o_grid.acpf.models.svc import adjust_svc_reactive_power
from o_grid.acpf.newton_raphson import solve_newton_raphson
from o_grid.acpf.reporting import LiveIterationReporter
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
        tolerance: float | None = None,
        max_iterations: int = 30,
        max_control_passes: int = 12,
        print_iterations: bool = False,
    ) -> Self | System:
        instance = super().__new__(cls)
        if system is None:
            return instance
        instance.tolerance = tolerance
        instance.max_iterations = max_iterations
        instance.max_control_passes = max_control_passes
        instance.print_iterations = print_iterations
        return instance.run(system).system

    def __init__(
        self,
        system: System | None = None,
        *,
        tolerance: float | None = None,
        max_iterations: int = 30,
        max_control_passes: int = 12,
        print_iterations: bool = False,
    ) -> None:
        del system
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.max_control_passes = max_control_passes
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
        settings = build_power_flow_settings(
            parsed,
            tolerance=self.tolerance,
            max_iterations=self.max_iterations,
        )
        reduction = reduce_closed_switches(case)
        numerical_case = reduction.case
        ybus = build_ybus(numerical_case)
        assign_island_reference_buses(numerical_case, ybus)
        has_lcc = bool(numerical_case.lccs)
        use_newton = self.solver_name == "newton-raphson" or has_lcc
        solve = solve_newton_raphson if use_newton else solve_fast_decoupled
        live_reporter = (
            LiveIterationReporter("newton-raphson" if use_newton else "fast-decoupled")
            if self.print_iterations
            else None
        )
        if live_reporter is not None:
            live_reporter.start()
        solution = solve(
            numerical_case,
            ybus,
            tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
            max_iterations=settings.max_iterations,
            iteration_callback=live_reporter.callback if live_reporter is not None else None,
            **(
                {
                    "max_angle_step": settings.max_angle_step,
                    "max_voltage_step": settings.max_voltage_step,
                }
                if solve is solve_fast_decoupled
                else {}
            ),
        )
        if self.solver_name == "fast-decoupled" and has_lcc:
            solution.fallback_used = True
        if live_reporter is not None:
            if solution.converged:
                live_reporter.accept("Base solve")
            else:
                live_reporter.fail("Base solve")
        rejected_controls: set[str] = set()
        for control_pass in range(self.max_control_passes):
            if solution.diverged:
                break
            accepted_any = False
            changed_any = False
            control_names = ["SVC", "switched shunt", "LTC", "LCC"]
            if control_pass == 0:
                control_names.insert(0, "bus limits")
            for control_name in control_names:
                if control_name in rejected_controls:
                    continue
                accepted_case = deepcopy(numerical_case)
                accepted_solution = solution
                trial_voltage = solution.voltage.copy()
                if control_name == "bus limits":
                    changed, trial_voltage = apply_bus_limit_controls(
                        numerical_case, ybus, trial_voltage, settings
                    )
                elif control_name == "SVC":
                    changed = adjust_svc_reactive_power(numerical_case, trial_voltage)
                elif control_name == "switched shunt":
                    changed = adjust_switched_shunts(numerical_case, trial_voltage)
                elif control_name == "LTC":
                    changed = adjust_ltc_taps(numerical_case, trial_voltage)
                else:
                    changed = update_lcc_from_dc_solution(numerical_case, trial_voltage)
                if not changed:
                    continue
                changed_any = True
                trial_ybus = build_ybus(numerical_case)
                phase = f"Control pass {control_pass + 1}: {control_name}"
                trial_trace = []
                if use_newton:
                    next_solution = solve_newton_raphson(
                        numerical_case,
                        trial_ybus,
                        tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
                        max_iterations=settings.max_iterations,
                        initial_voltage=trial_voltage,
                        iteration_callback=trial_trace.append if live_reporter else None,
                    )
                else:
                    next_solution = solve_fast_decoupled(
                        numerical_case,
                        trial_ybus,
                        tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
                        max_iterations=settings.max_iterations,
                        max_angle_step=settings.max_angle_step,
                        max_voltage_step=settings.max_voltage_step,
                        iteration_callback=trial_trace.append if live_reporter else None,
                    )
                next_solution.fallback_used = solution.fallback_used
                if not next_solution.converged:
                    if live_reporter is not None:
                        live_reporter.reject(phase)
                    rejected_controls.add(control_name)
                    numerical_case = accepted_case
                    reduction.case = numerical_case
                    ybus = build_ybus(numerical_case)
                    solution = accepted_solution
                    continue
                if live_reporter is not None:
                    live_reporter.begin_phase(phase)
                    for iteration in trial_trace:
                        live_reporter.emit(iteration)
                    live_reporter.accept(phase)
                solution = next_solution
                ybus = trial_ybus
                reduction.case = numerical_case
                accepted_any = True
            if not changed_any or not accepted_any:
                break
        if self.solver_name == "fast-decoupled" and not solution.converged:
            logger.warning(
                "Fast-decoupled power flow did not converge; retrying with Newton-Raphson "
                "from the decoupled voltage state."
            )
            if live_reporter is not None:
                live_reporter.begin_phase("Newton-Raphson fallback")
            solution = solve_newton_raphson(
                numerical_case,
                ybus,
                tolerance=min(settings.active_tolerance, settings.reactive_tolerance),
                max_iterations=settings.max_iterations,
                initial_voltage=solution.voltage,
                iteration_callback=live_reporter.callback if live_reporter is not None else None,
            )
            solution.fallback_used = True
            if live_reporter is not None:
                if solution.converged:
                    live_reporter.accept("Newton-Raphson fallback")
                else:
                    live_reporter.fail("Newton-Raphson fallback")
        refresh_lcc_reporting_state(numerical_case, solution.voltage)
        reduction.sync_control_state(case)
        solution.voltage = reduction.expand_voltage(solution.voltage)
        result_ybus = build_ybus(case)
        result = ACPowerFlowResult(
            solver=self.solver_name,
            converged=solution.converged,
            diverged=solution.diverged,
            iterations=solution.iterations,
            max_mismatch=solution.max_mismatch,
            fallback_used=solution.fallback_used,
            base_mva=case.base_mva,
            iteration_trace=solution.trace,
            buses=calculate_bus_results(case, result_ybus, solution.voltage),
            branches=calculate_branch_results(case, solution.voltage),
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
        report = live_reporter.finish() if live_reporter is not None else ""
        if result.converged:
            logger.success(
                "{} power flow converged in {} iteration(s); max mismatch {:.4e} pu.",
                self.solver_name,
                result.iterations + 1,
                result.max_mismatch or 0.0,
            )
        else:
            logger.error(
                "{} power flow {} after {} iteration(s); max mismatch {:.4e} pu.",
                self.solver_name,
                "diverged" if result.diverged else "did not converge",
                result.iterations + 1,
                result.max_mismatch or 0.0,
            )
        return PowerFlowRun(parsed=parsed, result=result, stdout=report)


class NewtonRaphsonPowerFlow(PowerFlowSolver):
    """Sparse full Newton-Raphson AC power-flow solver."""

    solver_name = "newton-raphson"


class FastDecoupledPowerFlow(PowerFlowSolver):
    """Sparse fast-decoupled AC power-flow solver."""

    solver_name = "fast-decoupled"
