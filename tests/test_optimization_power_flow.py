from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from loguru import logger
from pyomo.opt import TerminationCondition

from o_grid import OptimizationACPowerFlow
from o_grid.acpf.models import (
    build_power_flow_case,
    build_power_flow_settings,
    reduce_closed_switches,
)
from o_grid.acpf.optimization import (
    _parse_ipopt_iterations,
    build_optimization_model,
    solution_metrics,
    solve_optimization_model,
    summarize_solution,
)
from o_grid.models import ACBus, ACBusTypes
from o_grid.parser import AnaredeInfrasysParser
from o_grid.system import AnaredeSystem

DATA = Path(__file__).parent / "data" / "pwf"


def _build_solved_model(pwf: str, *, qlim_enabled: bool = False, strict: bool = False):
    parsed = AnaredeInfrasysParser().parse(DATA / pwf)
    case = build_power_flow_case(parsed)
    settings = build_power_flow_settings(parsed)
    numerical_case = reduce_closed_switches(case).case
    model = build_optimization_model(
        numerical_case,
        active_tolerance_pu=max(settings.active_tolerance, 1e-12),
        reactive_tolerance_pu=max(settings.reactive_tolerance, 1e-12),
        control_tolerance_pu=max(settings.control_tolerance, 1e-12),
        qlim_enabled=qlim_enabled or "QLIM" in settings.options,
        strict_voltage_limits=strict,
    )
    return parsed, numerical_case, model


def test_optimization_solver_runs_from_pwf_path() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = OptimizationACPowerFlow().run(parsed)

    assert run.result.converged is True
    assert run.result.diverged is False
    assert run.result.solver == "optimization"
    assert run.result.iterations > 0
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch <= 1.0e-3
    assert run.result.iteration_trace
    assert run.system is run.parsed.system
    assert len(run.result.buses) == 9
    assert "Optimization power-flow summary" in run.stdout
    assert all(
        isinstance(bus, ACBus) and bus.solved_voltage is not None
        for bus in parsed.components_by_block["DBAR"]
    )


def test_optimization_constructor_returns_solved_infrasys_system() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    solved = OptimizationACPowerFlow(parsed.system)

    assert isinstance(solved, AnaredeSystem)
    assert solved is parsed.system
    assert solved.power_flow_results is not None
    assert solved.power_flow_results.information.converged is True


def test_optimization_solver_converges_large_case_with_svc() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "CASO_FINAL_EQV2020.pwf")

    run = OptimizationACPowerFlow().run(parsed)

    assert run.result.converged is True
    assert run.result.solver == "optimization"
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch <= 5.1e-3


def test_optimization_solver_runs_from_system_instance() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = OptimizationACPowerFlow().run(parsed.system)

    assert run.result.converged is True
    assert run.result.solver == "optimization"


def test_optimization_solver_defaults() -> None:
    solver = OptimizationACPowerFlow()

    assert isinstance(solver, OptimizationACPowerFlow)
    assert solver.solver_name == "optimization"
    assert solver.max_iterations == 30
    assert solver.max_control_passes == 12
    assert solver.strict_voltage_limits is False
    assert solver.objective_function == "minimize_residuals"


def test_optimization_solver_rejects_unknown_objective_function() -> None:
    with pytest.raises(ValueError, match="Unknown objective_function"):
        OptimizationACPowerFlow(objective_function="not-a-real-objective")


def test_optimization_solver_runs_zero_function_objective() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = OptimizationACPowerFlow(objective_function="zero_function").run(parsed)

    assert run.result.converged is True
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch <= 1.0e-6
    assert "Objective function: zero_function" in run.stdout


def test_optimization_solver_runs_squared_generation_objective() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = OptimizationACPowerFlow(objective_function="squared_generation").run(parsed)

    assert run.result.converged is True
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch <= 1.0e-6
    assert "Objective function: squared_generation" in run.stdout


def test_optimization_solver_objective_function_with_system_constructor() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    solved = OptimizationACPowerFlow(
        system=parsed.system,
        objective_function="zero_function",
        max_iterations=30,
    )

    assert isinstance(solved, AnaredeSystem)
    assert solved is parsed.system
    assert solved.power_flow_results.information.converged is True


def test_optimization_model_build_solve_and_metrics() -> None:
    parsed, numerical_case, model = _build_solved_model("d_9nodes.pwf")

    assert list(model.BUS) == [bus.number for bus in numerical_case.buses]
    assert list(model.QPV) == []
    results, log, iterations = solve_optimization_model(model, max_iterations=30)

    assert results.solver.termination_condition is TerminationCondition.optimal
    assert iterations is not None
    metrics = solution_metrics(model)
    assert metrics["converged"] is True
    assert metrics["max_p"] <= 1.0e-3
    assert metrics["max_q"] <= 1.0e-3
    assert "Optimization power-flow summary" in summarize_solution(model)


def test_optimization_model_supports_strict_voltage_limits() -> None:
    parsed, _, model = _build_solved_model("d_9nodes.pwf", strict=True)

    results, _, _ = solve_optimization_model(model, max_iterations=30)

    assert results.solver.termination_condition is TerminationCondition.optimal
    assert solution_metrics(model)["converged"] is True


def test_optimization_model_zero_function_is_exact_feasibility() -> None:
    parsed, numerical_case, _ = _build_solved_model("d_9nodes.pwf")
    model = build_optimization_model(
        numerical_case,
        active_tolerance_pu=0.1,
        reactive_tolerance_pu=0.1,
        control_tolerance_pu=0.5,
        objective_function="zero_function",
    )

    results, _, iterations = solve_optimization_model(model, max_iterations=30)

    assert results.solver.termination_condition is TerminationCondition.optimal
    assert iterations is not None
    metrics = solution_metrics(model)
    assert metrics["converged"] is True
    assert metrics["max_p"] <= 1.0e-9
    assert metrics["max_q"] <= 1.0e-9
    assert pyo.value(model.p_slack_pos[model.BUS.first()]) == 0.0
    assert pyo.value(model.objective) > 0.0


def test_optimization_model_squared_generation_redispatches_slack() -> None:
    parsed, numerical_case, _ = _build_solved_model("d_9nodes.pwf")
    model = build_optimization_model(
        numerical_case,
        active_tolerance_pu=0.1,
        reactive_tolerance_pu=0.1,
        control_tolerance_pu=0.5,
        objective_function="squared_generation",
    )

    results, _, iterations = solve_optimization_model(model, max_iterations=30)

    assert results.solver.termination_condition is TerminationCondition.optimal
    assert iterations is not None
    assert solution_metrics(model)["converged"] is True
    assert solution_metrics(model)["max_p"] <= 1.0e-9
    slack_gen = sum(
        pyo.value(model.pg_slack[bus]) ** 2 for bus in model.SLACK_GEN
    )
    assert slack_gen > 0.0
    assert slack_gen < pyo.value(model.objective)


def test_optimization_solver_prints_iterations(capsys) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    solver = OptimizationACPowerFlow(print_iterations=True)
    run = solver.run(parsed)

    output = capsys.readouterr().out
    assert run.result.converged is True
    assert "Optimization power-flow summary" in run.stdout
    assert "Number of Iterations" in output


def test_optimization_model_handles_q_limited_pv_buses() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    case = build_power_flow_case(parsed)
    settings = build_power_flow_settings(parsed)
    numerical_case = reduce_closed_switches(case).case
    target = next(bus for bus in numerical_case.buses if bus.kind == ACBusTypes.PV)
    target.name = "EOL-500"
    target.base_voltage = 1000.0
    target.minimum_reactive_generation = -100.0
    target.maximum_reactive_generation = 100.0

    model = build_optimization_model(
        numerical_case,
        active_tolerance_pu=max(settings.active_tolerance, 1e-12),
        reactive_tolerance_pu=max(settings.reactive_tolerance, 1e-12),
        control_tolerance_pu=max(settings.control_tolerance, 1e-12),
        qlim_enabled=True,
    )

    assert target.number in model.QPV
    results, _, _ = solve_optimization_model(model, max_iterations=30)
    assert results.solver.termination_condition is TerminationCondition.optimal
    assert solution_metrics(model)["converged"] is True
    assert model.qg_qpv[target.number].value is not None


def test_parse_ipopt_iterations() -> None:
    log = "Number of Iterations....: 12\nRestoration Phase Iteration: 3\n"
    assert _parse_ipopt_iterations(log) == 12
    assert _parse_ipopt_iterations("no summary here") is None


def test_summarize_solution_reports_voltage_violations() -> None:
    _, _, model = _build_solved_model("d_9nodes.pwf")
    results, _, _ = solve_optimization_model(model, max_iterations=30)
    assert results.solver.termination_condition is TerminationCondition.optimal

    bus = next(iter(model.BUS))
    model.vm[bus].set_value(1.5)

    summary = summarize_solution(model)
    assert "Voltage above limit" in summary


def test_optimization_solver_reports_failed_run_when_ipopt_unavailable(monkeypatch) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    import o_grid.acpf.optimization as optimization

    monkeypatch.setattr(optimization, "solve_optimization_model", lambda *a, **k: (None, "", None))

    run = OptimizationACPowerFlow().run(parsed)

    assert run.result.converged is False
    assert run.result.diverged is True
    assert run.result.iterations == 0


@pytest.mark.parametrize(
    "termination",
    [
        TerminationCondition.infeasible,
        TerminationCondition.infeasibleOrUnbounded,
        TerminationCondition.unbounded,
        TerminationCondition.error,
    ],
)
def test_optimization_solver_marks_non_optimal_termination(monkeypatch, termination) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    import o_grid.acpf.optimization as optimization

    fake_results = SimpleNamespace(solver=SimpleNamespace(termination_condition=termination))
    monkeypatch.setattr(
        optimization, "solve_optimization_model", lambda *a, **k: (fake_results, "", 5)
    )

    run = OptimizationACPowerFlow().run(parsed)

    assert run.result.converged is False
    if termination in {
        TerminationCondition.infeasible,
        TerminationCondition.infeasibleOrUnbounded,
    }:
        message = StringIO()
        logger_id = logger.add(message, format="{message}", level="ERROR")
        try:
            OptimizationACPowerFlow().run(parsed)
        finally:
            logger.remove(logger_id)
        assert "Optimization AC power flow is infeasible after 5 iteration(s)" in message.getvalue()
    assert run.result.diverged is True
