from __future__ import annotations

from pathlib import Path

import pytest
from infrasys import Component
from loguru import logger

from o_grid import ACBusResults as TopLevelACBusResults
from o_grid.acpf import (
    ACBusResults,
    ACLineResults,
    ACOptimalPowerFlow,
    ControllableSeriesCompensatorResults,
    DCLineResults,
    FastDecoupledPowerFlow,
    LTCTransformerResults,
    NewtonRaphsonPowerFlow,
    PhaseShiftingTransformerResults,
    PrimeDualOPF,
    ResultsInformation,
    StaticVARCompensatorResults,
    StatisticResultsInformation,
    SwitchDeviceResults,
)
from o_grid.acpf.models import build_power_flow_case, build_power_flow_settings
from o_grid.models import ACBus, ACLine
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


def test_build_power_flow_case_excludes_unavailable_infrasys_branches() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    line = next(iter(parsed.system.get_components(ACLine)))
    line.available = False

    case = build_power_flow_case(parsed)

    assert len(case.branches) == 9


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
    settings = build_power_flow_settings(parsed)
    assert settings.active_tolerance == pytest.approx(0.001)
    assert settings.reactive_tolerance == pytest.approx(0.001)
    assert settings.control_tolerance == pytest.approx(0.005)
    assert run.result.max_mismatch <= max(settings.active_tolerance, settings.reactive_tolerance)
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
    assert results.information.bus_count == 9
    assert results.information.bus_count_after_reduction == 9
    assert results.information.branch_count == 10
    assert results.information.branch_count_after_reduction == 10
    assert not any(item.collapsed for item in results.ac_buses)
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
    assert "Base solve" in output
    assert "[Base solve accepted]" in output
    assert "Converged: yes" not in output


def test_solver_defaults_to_thirty_iterations() -> None:
    solver = NewtonRaphsonPowerFlow()

    assert isinstance(solver, NewtonRaphsonPowerFlow)
    assert solver.max_iterations == 30
    assert solver.max_control_passes == 12


def test_prime_dual_solver_reports_its_own_iterations(capsys) -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = PrimeDualOPF(max_iterations=20, print_iterations=True).run(parsed)

    output = capsys.readouterr().out
    assert run.result.solver == "primal-dual"
    assert "Iteration-by-iteration convergence trace (Primal-dual OPF)" in output
    assert "Iteration-by-iteration convergence trace (Newton-Raphson)" not in output
    assert "  0  " in output


def test_primal_dual_opf_converges_and_attaches_results() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = ACOptimalPowerFlow(max_iterations=20).run(parsed)

    assert run.result.solver == "primal-dual"
    assert run.result.converged is True
    assert run.result.diverged is False
    assert run.result.iterations > 0
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch < 1.0e-3
    assert len(run.result.iteration_trace) == run.result.iterations + 1
    assert all(bus.solved_voltage is not None for bus in parsed.components_by_block["DBAR"])


def test_solver_runs_from_pwf_path() -> None:
    solver = NewtonRaphsonPowerFlow()

    run = solver.run(DATA / "d_9nodes.pwf")

    assert run.result.converged is True
    assert run.result.solver == "newton-raphson"
    assert run.system is not None


def test_fast_decoupled_with_lcc_marks_fallback() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "CASO_FINAL_EQV2020.pwf")

    run = FastDecoupledPowerFlow().run(parsed)

    assert run.result.converged is True
    assert run.result.fallback_used is True


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
    assert results.information.bus_count == 247
    assert results.information.bus_count_after_reduction < results.information.bus_count
    assert results.information.branch_count_after_reduction < results.information.branch_count
    assert any(item.collapsed for item in results.ac_buses)
    assert all(
        item.representative_bus != item.bus_number for item in results.ac_buses if item.collapsed
    )
    assert len(results.generators) == 56
    assert len(results.transformers) == 302
    assert len(results.ltc_transformers) == 12
    assert len(results.static_var_compensators) == 6
    assert len(results.dc_lines) == 28
    assert all(item.target_voltage_pu is not None for item in results.ltc_transformers)
    assert results.generators[0].generator_type == "Nuclear"
    assert results.generators[0].reserve_mw == pytest.approx(
        results.generators[0].maximum_active_generation_mw
        - results.generators[0].active_generation_mw
    )
    branch_rows = [
        *results.ac_lines,
        *results.transformers,
        *results.ltc_transformers,
        *results.phase_shifting_transformers,
        *results.controllable_series_compensators,
    ]
    assert all(0.0 <= item.power_factor_from <= 1.0 for item in branch_rows)
    assert all(0.0 <= item.power_factor_to <= 1.0 for item in branch_rows)
    assert all(item.reactive_type_from in {"Cap", "Ind", "-"} for item in branch_rows)
    assert all(item.reactive_type_to in {"Cap", "Ind", "-"} for item in branch_rows)
    assert all(item.bus_name for item in results.static_var_compensators)
    assert sum(item.converter_type == "Rectifier" for item in results.dc_lines) == 14
    assert sum(item.converter_type == "Inverter" for item in results.dc_lines) == 14
    assert all(item.bus_name for item in results.dc_lines)
    assert all(item.loss_mw is not None for item in results.dc_lines)
    assert all(item.dc_voltage_kv is not None for item in results.dc_lines)
    assert all(item.dc_current_pu is not None for item in results.dc_lines)
    assert all(item.dc_current_a is not None for item in results.dc_lines)
    assert all(item.firing_angle_deg is not None for item in results.dc_lines)
    assert all(item.overlap_angle_deg is not None for item in results.dc_lines)
    assert any((item.overlap_angle_deg or 0.0) > 0.0 for item in results.dc_lines)
    assert all(item.tap_pu is not None for item in results.dc_lines)
    assert sum(item.control_mode == "Slack" for item in results.dc_lines) == 14
    assert sum(item.control_mode == "Power" for item in results.dc_lines) == 14
    assert len(list(solved.get_components(LTCTransformerResults))) == 12
    assert len(list(solved.get_components(StaticVARCompensatorResults))) == 6
    assert len(list(solved.get_components(DCLineResults))) == 28
    assert results.information.dc_line_count == 14
    information = results.information
    assert information.solver_mode == "sparse direct full Newton solve"
    settings = build_power_flow_settings(parsed)
    assert information.convergence_tolerance_pu == pytest.approx(
        min(settings.active_tolerance, settings.reactive_tolerance)
    )
    assert information.scheduled_generation_mw == pytest.approx(110098.618, abs=1e-3)
    assert information.solved_generation_mw == pytest.approx(110112.055, abs=1e-3)
    assert information.total_load_mw == pytest.approx(109228.117)
    assert information.branch_active_losses_mw == pytest.approx(883.938, abs=1e-3)

    solved.info()
    output = capsys.readouterr().out
    assert "Statistic Results Information" in output
    assert "Estimated dense matrix memory" in output
    assert "Voltage upper violations" in output


def test_dccv_rectifier_slack_balances_dc_losses() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "CASO_FINAL_EQV2020.pwf")
    controls = parsed.components_by_block["DCCV"]
    controls[0].ext["pwf_values"]["slack"] = "F"
    controls[1].ext["pwf_values"]["slack"] = "N"

    case = build_power_flow_case(parsed)
    assert case.lccs is not None
    lcc = case.lccs[0]
    loss_mw = lcc.current_ka**2 * lcc.rdc_ohm

    assert lcc.rectifier_slack is True
    assert lcc.inverter_slack is False
    assert lcc.rectifier_control_mode == "Slack"
    assert lcc.inverter_control_mode == "Power"
    assert lcc.vdc_rectifier_kv == pytest.approx(lcc.vdc_inverter_kv + lcc.current_ka * lcc.rdc_ohm)
    assert lcc.p_rectifier_mw == pytest.approx(lcc.p_inverter_mw + loss_mw)
