from __future__ import annotations

from pathlib import Path

import pytest
from infrasys import Component
from loguru import logger

from o_grid import ACBusResults as TopLevelACBusResults
from o_grid.acpf import (
    ACBusResults,
    ACLineResults,
    ControllableSeriesCompensatorResults,
    DCLineResults,
    FastDecoupledPowerFlow,
    LTCTransformerResults,
    NewtonRaphsonPowerFlow,
    PhaseShiftingTransformerResults,
    ResultsInformation,
    StaticVARCompensatorResults,
    StatisticResultsInformation,
    SwitchDeviceResults,
)
from o_grid.acpf.models import build_power_flow_case
from o_grid.models import ACBus
from o_grid.parser import AnaredeInfrasysParser
from o_grid.system import AnaredeSystem

DATA = Path(__file__).parent / "data" / "pwf"


@pytest.mark.parametrize(
    ("result_type", "fields"),
    [
        (
            ACBusResults,
            {
                "bus_number",
                "bus_name",
                "bus_type",
                "area",
                "in_service",
                "voltage_pu",
                "voltage_kv",
                "angle_deg",
                "active_generation_mw",
                "reactive_generation_mvar",
                "active_load_mw",
                "reactive_load_mvar",
                "minimum_voltage_pu",
                "maximum_voltage_pu",
                "violation",
                "representative_bus",
                "collapsed",
            },
        ),
        (
            ACLineResults,
            {
                "line_number",
                "from_bus",
                "to_bus",
                "circuit",
                "resistance_pu",
                "reactance_pu",
                "charging_pu",
                "tap_pu",
                "phase_shift_deg",
                "rating_mva",
                "active_from_mw",
                "reactive_from_mvar",
                "active_to_mw",
                "reactive_to_mvar",
                "loading_percent",
                "active_loss_mw",
                "reactive_loss_mvar",
                "violation",
            },
        ),
        (
            LTCTransformerResults,
            {
                "device_number",
                "from_bus",
                "to_bus",
                "circuit",
                "controlled_bus",
                "tap_pu",
                "minimum_tap_pu",
                "maximum_tap_pu",
                "target_voltage_pu",
                "active_from_mw",
                "reactive_from_mvar",
                "active_to_mw",
                "reactive_to_mvar",
            },
        ),
        (
            PhaseShiftingTransformerResults,
            {
                "device_number",
                "from_bus",
                "to_bus",
                "circuit",
                "controlled_bus",
                "phase_shift_deg",
                "minimum_phase_shift_deg",
                "maximum_phase_shift_deg",
                "target_active_power_mw",
                "active_from_mw",
                "reactive_from_mvar",
                "active_to_mw",
                "reactive_to_mvar",
            },
        ),
        (
            SwitchDeviceResults,
            {
                "device_number",
                "from_bus",
                "to_bus",
                "circuit",
                "active_from_mw",
                "reactive_from_mvar",
                "active_to_mw",
                "reactive_to_mvar",
                "loading_percent",
                "active_loss_mw",
                "reactive_loss_mvar",
                "status",
            },
        ),
        (
            StaticVARCompensatorResults,
            {
                "device_number",
                "bus_number",
                "bus_name",
                "controlled_bus",
                "mode",
                "voltage_pu",
                "reference_voltage_pu",
                "slope_percent",
                "reactive_power_mvar",
                "initial_reactive_power_mvar",
                "reactive_power_delta_mvar",
                "minimum_reactive_power_mvar",
                "maximum_reactive_power_mvar",
                "status",
                "equation_residual",
            },
        ),
        (
            ControllableSeriesCompensatorResults,
            {
                "device_number",
                "from_bus",
                "to_bus",
                "circuit",
                "mode",
                "reactance_pu",
                "minimum_reactance_pu",
                "maximum_reactance_pu",
                "active_from_mw",
                "reactive_from_mvar",
                "active_to_mw",
                "reactive_to_mvar",
                "status",
            },
        ),
        (
            DCLineResults,
            {
                "bus_number",
                "bus_name",
                "voltage_pu",
                "converter_type",
                "pole_number",
                "control_mode",
                "active_power_mw",
                "reactive_power_mvar",
                "loss_mw",
                "dc_voltage_kv",
                "dc_current_pu",
                "dc_current_a",
                "firing_angle_deg",
                "overlap_angle_deg",
                "power_factor_angle_deg",
                "tap_pu",
                "status",
            },
        ),
    ],
)
def test_result_components_match_workbook_columns(result_type, fields: set[str]) -> None:
    assert issubclass(result_type, Component)
    assert result_type.model_fields.keys() >= fields


def test_result_components_are_exported_from_top_level_package() -> None:
    assert TopLevelACBusResults is ACBusResults


def test_build_power_flow_case_uses_system_components() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    case = build_power_flow_case(parsed)

    assert len(case.buses) == 9
    assert len(case.branches) == 10
    assert case.base_mva == 100.0


@pytest.mark.parametrize(
    ("solver_type", "solver_name"),
    [
        (NewtonRaphsonPowerFlow, "newton-raphson"),
        (FastDecoupledPowerFlow, "fast-decoupled"),
    ],
)
def test_python_solver_updates_parsed_system(solver_type, solver_name: str) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    run = solver_type().run(parsed)
    buses = run.parsed.components_by_block["DBAR"]

    assert run.result.converged is True
    assert run.result.solver == solver_name
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch <= 1e-6
    assert run.result.iteration_trace
    assert run.result.iteration_trace[-1].iteration == run.result.iterations
    assert len(run.result.buses) == 9
    assert run.system is run.parsed.system
    assert all(isinstance(bus, ACBus) for bus in buses)
    assert all(bus.solved_voltage is not None for bus in buses)
    assert all("power_flow" in bus.ext for bus in buses)


def test_newton_raphson_constructor_returns_solved_infrasys_system(capsys) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    solved = NewtonRaphsonPowerFlow(parsed.system)

    assert isinstance(solved, AnaredeSystem)
    assert solved is parsed.system
    assert solved.power_flow_results is not None
    results = solved.power_flow_results
    assert results.information.converged is True
    assert results.information.solver == "newton-raphson"
    assert len(results.ac_buses) == 9
    assert len(results.ac_lines) == 8
    assert len(list(solved.get_components(ACBusResults))) == 9
    assert len(list(solved.get_components(ACLineResults))) == 8
    assert len(list(solved.get_components(ResultsInformation))) == 1
    assert len(list(solved.get_components(StatisticResultsInformation))) == 1
    assert ACBusResults.model_fields.keys() >= {
        "voltage_pu",
        "voltage_kv",
        "active_generation_mw",
        "reactive_generation_mvar",
        "violation",
    }

    solved.info()
    output = capsys.readouterr().out
    assert output.index("Power Flow Information") < output.index("Results Information")
    assert "ACBusResults" in output
    assert "ACLineResults" in output
    results_output = output[output.index("Results Information") :]
    assert "Type" in results_output
    assert "Count" in results_output
    assert "Max Mismatch (pu)" not in results_output
    assert "Voltage Upper Violations" not in results_output
    assert "Statistic Results Information" in results_output
    assert "AC convergence criterion" in results_output
    assert "Generation - load - branch losses" in results_output


def test_solver_prints_and_retains_requested_report(capsys) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    solver = NewtonRaphsonPowerFlow(print_iterations=True)
    assert isinstance(solver, NewtonRaphsonPowerFlow)

    run = solver.run(parsed)

    output = capsys.readouterr().out
    assert run.stdout == output.rstrip()
    assert "Iteration-by-iteration convergence trace (Newton-Raphson)" in output
    assert "Converged: yes" not in output


@pytest.mark.parametrize(
    ("max_iterations", "expected_level"),
    [(50, "SUCCESS"), (0, "ERROR")],
)
def test_solver_always_logs_outcome(max_iterations: int, expected_level: str) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    messages: list[tuple[str, str]] = []
    sink = logger.add(
        lambda message: messages.append((message.record["level"].name, message.record["message"]))
    )
    try:
        solver = NewtonRaphsonPowerFlow(max_iterations=max_iterations)
        assert isinstance(solver, NewtonRaphsonPowerFlow)
        solver.run(parsed)
    finally:
        logger.remove(sink)

    assert any(
        level == expected_level and "newton-raphson power flow" in message
        for level, message in messages
    )


def test_controllable_series_compensator_has_typed_flow_result() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_33nodes_dcer_dcsc.pwf")

    solved = NewtonRaphsonPowerFlow(parsed.system)

    assert isinstance(solved, AnaredeSystem)
    assert solved.power_flow_results is not None
    results = solved.power_flow_results
    assert results.information.converged is True
    assert len(results.static_var_compensators) == 8
    assert len(results.controllable_series_compensators) == 1


def test_workbook_results_cover_ltc_svc_and_dc_components(capsys) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "CASO_FINAL_EQV2020.pwf")

    solved = NewtonRaphsonPowerFlow(parsed.system)

    assert isinstance(solved, AnaredeSystem)
    assert solved.power_flow_results is not None
    results = solved.power_flow_results
    assert results.information.converged is True
    assert len(results.ltc_transformers) == 12
    assert len(results.static_var_compensators) == 6
    assert len(results.dc_lines) == 14
    assert all(item.target_voltage_pu is not None for item in results.ltc_transformers)
    assert all(item.bus_name for item in results.static_var_compensators)
    assert any(item.active_power_mw is not None for item in results.dc_lines)
    assert len(list(solved.get_components(LTCTransformerResults))) == 12
    assert len(list(solved.get_components(StaticVARCompensatorResults))) == 6
    assert len(list(solved.get_components(DCLineResults))) == 14
    information = results.information
    assert information.solver_mode == "sparse direct full Newton solve"
    assert information.convergence_tolerance_pu == pytest.approx(1e-6)
    assert information.scheduled_generation_mw == pytest.approx(110099.870)
    assert information.solved_generation_mw == pytest.approx(110070.697, abs=1e-3)
    assert information.total_load_mw == pytest.approx(109228.117)
    assert information.branch_active_losses_mw == pytest.approx(842.580, abs=1e-3)

    solved.info()
    output = capsys.readouterr().out
    assert "Statistic Results Information" in output
    assert "Estimated dense matrix memory" in output
    assert "Voltage upper violations" in output
