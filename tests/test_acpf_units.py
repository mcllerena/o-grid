from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from o_grid.acpf.controls import apply_bus_limit_controls
from o_grid.acpf.models import PowerFlowCase, build_lcc_data
from o_grid.acpf.models.case import BranchData, BusData
from o_grid.acpf.models.csc import apply_csc_to_branches, is_active_csc
from o_grid.acpf.models.lcc import (
    LCCData,
    build_lcc_injections,
    refresh_lcc_reporting_state,
    update_lcc_from_dc_solution,
)
from o_grid.acpf.models.ltc import adjust_ltc_taps
from o_grid.acpf.models.pst import apply_pst_to_branch
from o_grid.acpf.models.settings import PowerFlowSettings
from o_grid.acpf.models.svc import (
    SVCData,
    SVCState,
    adjust_svc_reactive_power,
    build_svc_states,
    refresh_decoupled_svc_controls,
    svc_control_derivative_q,
    svc_control_derivative_voltage,
    svc_control_residual,
    svc_q_injection_by_bus,
    sync_svc_states_to_case,
    update_svc_limits,
)
from o_grid.acpf.reporting import LiveIterationReporter, format_power_flow_report
from o_grid.acpf.results import (
    ACPowerFlowResult,
    BusPowerFlowResult,
    IterationPowerFlowResult,
    apply_power_flow_result,
)
from o_grid.acpf.utils.network import (
    assign_island_reference_buses,
    build_ybus,
)
from o_grid.models import ACBusTypes
from o_grid.parser import ParsedAnaredeSystem
from o_grid.system import AnaredeSystem


def _bus(number: int, kind: ACBusTypes = ACBusTypes.PQ, voltage: float = 1.0, **kwargs) -> BusData:
    data = dict(
        number=number,
        name=str(number),
        kind=kind,
        voltage=voltage,
        angle=0.0,
        active_generation=0.0,
        reactive_generation=0.0,
        active_load=0.0,
        reactive_load=0.0,
        shunt_susceptance=0.0,
        minimum_voltage=0.9,
        maximum_voltage=1.1,
        base_voltage=100.0,
        voltage_group="A",
    )
    data.update(kwargs)
    return BusData(**data)


def _branch(
    from_bus: int,
    to_bus: int,
    *,
    resistance: float = 0.01,
    reactance: float = 0.1,
    circuit: int = 1,
    **kwargs,
) -> BranchData:
    data = dict(
        from_bus=from_bus,
        to_bus=to_bus,
        circuit=circuit,
        resistance=resistance,
        reactance=reactance,
        charging=0.0,
        tap=1.0,
        phase_shift=0.0,
        rating=100.0,
    )
    data.update(kwargs)
    return BranchData(**data)


def _case(
    buses: list[BusData],
    branches: list[BranchData] | None = None,
    *,
    svcs: list[SVCData] | None = None,
    lccs: list[LCCData] | None = None,
) -> PowerFlowCase:
    return PowerFlowCase(
        base_mva=100.0,
        buses=buses,
        branches=branches or [],
        svcs=svcs or [],
        shunt_controls=[],
        lccs=lccs or [],
    )


def _settings(*options: str) -> PowerFlowSettings:
    return PowerFlowSettings(
        base_mva=100.0,
        active_tolerance=0.001,
        reactive_tolerance=0.001,
        control_tolerance=0.005,
        max_iterations=30,
        voltage_divergence_min=0.4,
        voltage_divergence_max=2.0,
        max_angle_step=0.5,
        max_voltage_step=0.1,
        max_csc_step=0.01,
        low_impedance_threshold=2e-4,
        options=frozenset(options),
    )


class _PstComponent:
    ext = {"pwf_values": {"phase_shift": 15.0}}
    r = 1.5
    x = 8.0


def test_apply_pst_to_branch_sets_phase_shift_and_impedance() -> None:
    branch = _branch(1, 2)

    apply_pst_to_branch(_PstComponent(), branch)

    assert branch.phase_shift == pytest.approx(-math.radians(15.0))
    assert branch.resistance == pytest.approx(1.5 * 0.01)
    assert branch.reactance == pytest.approx(8.0 * 0.01)


def test_apply_pst_to_branch_without_impedance_overrides() -> None:
    class _PlainPst:
        ext = None
        r = None
        x = None

    branch = _branch(1, 2)

    apply_pst_to_branch(_PlainPst(), branch)

    assert branch.phase_shift == pytest.approx(0.0)
    assert branch.resistance == pytest.approx(0.01)


def test_apply_bus_limit_controls_converts_over_reactive_pv_bus() -> None:
    bus = _bus(
        1,
        kind=ACBusTypes.PV,
        reactive_load=200.0,
        minimum_reactive_generation=-50.0,
        maximum_reactive_generation=50.0,
    )
    case = _case([bus])
    ybus = build_ybus(case)

    changed, voltage = apply_bus_limit_controls(
        case, ybus, np.array([1.0 + 0.0j]), _settings("QLIM")
    )

    assert changed is True
    assert bus.kind == ACBusTypes.PQ
    assert bus.reactive_generation == pytest.approx(50.0)
    assert voltage[0] == pytest.approx(1.0)


def test_apply_bus_limit_controls_raises_high_voltage_pq_bus() -> None:
    bus = _bus(1, kind=ACBusTypes.PQ, voltage=1.2, minimum_voltage=0.9, maximum_voltage=1.1)
    case = _case([bus])

    changed, voltage = apply_bus_limit_controls(
        case, build_ybus(case), np.array([1.2 + 0.0j]), _settings("VLIM")
    )

    assert changed is True
    assert bus.kind == ACBusTypes.PV
    assert bus.voltage == pytest.approx(1.1)
    assert voltage[0] == pytest.approx(1.1)


def test_apply_bus_limit_controls_lowers_low_voltage_pq_bus() -> None:
    bus = _bus(1, kind=ACBusTypes.PQ, voltage=0.8, minimum_voltage=0.9, maximum_voltage=1.1)
    case = _case([bus])

    changed, voltage = apply_bus_limit_controls(
        case, build_ybus(case), np.array([0.8 + 0.0j]), _settings("VLIM")
    )

    assert changed is True
    assert bus.kind == ACBusTypes.PV
    assert bus.voltage == pytest.approx(0.9)
    assert voltage[0] == pytest.approx(0.9)


class _InactiveCsc:
    available = False
    ext = {"pwf_values": {"from_bus": 1, "to_bus": 2}}


class _ActiveCsc:
    available = True
    ext = {
        "pwf_values": {
            "from_bus": 1,
            "to_bus": 2,
            "initial_reactance": 5.0,
            "dcsc_capacity": 100.0,
        }
    }


class _InvalidCircuitCsc:
    available = True
    dcsc_circuit = "not-a-number"
    ext = {"pwf_values": {"from_bus": 1, "to_bus": 2, "initial_reactance": 5.0}}


def test_is_active_csc_respects_operation_and_state() -> None:
    assert is_active_csc(_ActiveCsc()) is True
    assert is_active_csc(_InactiveCsc()) is False


def test_apply_csc_to_branches_skips_inactive_components() -> None:
    branches: list[BranchData] = []

    apply_csc_to_branches([_InactiveCsc()], branches, BranchData)

    assert branches == []


def test_apply_csc_to_branches_merges_into_existing_branch() -> None:
    branch = _branch(1, 2, reactance=0.05)

    apply_csc_to_branches([_ActiveCsc()], [branch], BranchData)

    assert branch.reactance == pytest.approx(0.1)


def test_apply_csc_to_branches_stamps_standalone_branch_for_invalid_circuit() -> None:
    branches: list[BranchData] = []

    apply_csc_to_branches([_InvalidCircuitCsc()], branches, BranchData)

    assert len(branches) == 1
    assert branches[0].from_bus == 1
    assert branches[0].to_bus == 2
    assert branches[0].circuit == 1
    assert branches[0].reactance == pytest.approx(0.05)


def test_adjust_ltc_taps_stops_at_tap_limit() -> None:
    branch = _branch(
        1,
        2,
        tap=0.9,
        controlled_bus=1,
        minimum_tap=0.9,
        maximum_tap=1.1,
        target_voltage=1.0,
    )
    case = _case([_bus(1, kind=ACBusTypes.PV), _bus(2)], branches=[branch])

    changed = adjust_ltc_taps(case, np.array([1.1 + 0.0j, 1.0 + 0.0j]))

    assert changed is False


def test_adjust_svc_reactive_power_skips_bus_at_target() -> None:
    svc = SVCData(
        bus=1,
        controlled_bus=1,
        mode="I",
        slope=0.05,
        reactive_power=0.0,
        minimum_reactive_power=-100.0,
        maximum_reactive_power=100.0,
        reference_voltage=1.0,
    )
    case = _case([_bus(1)], svcs=[svc])

    changed = adjust_svc_reactive_power(case, np.array([1.0 + 0.0j]))

    assert changed is False


def test_build_svc_states_only_activates_pq_buses() -> None:
    svc = SVCData(
        bus=1,
        controlled_bus=1,
        mode="I",
        slope=0.05,
        reactive_power=20.0,
        minimum_reactive_power=-100.0,
        maximum_reactive_power=100.0,
        reference_voltage=1.02,
    )
    case = _case([_bus(1, kind=ACBusTypes.PV)], svcs=[svc])

    states = build_svc_states(case, np.array([1.01 + 0.0j]))

    assert len(states) == 1
    assert states[0].active is False
    assert states[0].q_pu == 0.0

    case = _case([_bus(1)], svcs=[svc])
    states = build_svc_states(case, np.array([1.01 + 0.0j]))

    assert states[0].active is True
    assert states[0].q_pu == pytest.approx(0.2)
    assert states[0].v_ref == pytest.approx(1.02)


def test_svc_control_residual_matches_reference_droop() -> None:
    state = SVCState(
        device_index=0,
        bus_index=1,
        control_bus_index=1,
        active=True,
        mode="P",
        slope=0.02,
        q_pu=0.5,
        q_min_pu=-1.0,
        q_max_pu=1.0,
        v_ref=1.0,
    )
    vm = np.array([1.0, 1.04, 1.0])

    assert svc_control_residual(state, vm) == pytest.approx(1.04 - 1.0 + 0.5 * 0.02)

    state.mode = "I"
    assert svc_control_residual(state, vm) == pytest.approx(1.04 - 1.0 + 0.5 * 0.02 / 1.04)

    state.limit_state = -1
    assert svc_control_residual(state, vm) == pytest.approx(-1.0 * 1.04**2 - 0.5)
    state.limit_state = 1
    assert svc_control_residual(state, vm) == pytest.approx(1.0 * 1.04**2 - 0.5)


def test_svc_control_derivatives_match_reference() -> None:
    state = SVCState(
        device_index=0,
        bus_index=2,
        control_bus_index=1,
        active=True,
        mode="I",
        slope=0.02,
        q_pu=0.5,
        q_min_pu=-1.0,
        q_max_pu=1.0,
        v_ref=1.0,
    )
    vm = np.array([1.0, 1.04, 1.05])

    assert svc_control_derivative_voltage(state, 1, vm) == pytest.approx(1.0)
    assert svc_control_derivative_voltage(state, 2, vm) == pytest.approx(-0.5 * 0.02 / 1.05**2)
    assert svc_control_derivative_q(state, vm) == pytest.approx(0.02 / 1.05)

    state.mode = "P"
    assert svc_control_derivative_q(state, vm) == pytest.approx(0.02)

    state.limit_state = -1
    assert svc_control_derivative_voltage(state, 1, vm) == pytest.approx(2.0 * -1.0 * 1.04)
    assert svc_control_derivative_q(state, vm) == pytest.approx(-1.0)


def test_update_svc_limits_clamps_and_sets_limit_state() -> None:
    state = SVCState(
        device_index=0,
        bus_index=0,
        control_bus_index=0,
        active=True,
        mode="P",
        slope=0.02,
        q_pu=0.0,
        q_min_pu=-1.0,
        q_max_pu=1.0,
        v_ref=0.95,
    )
    vm = np.array([0.96, 1.0])
    update_svc_limits([state], vm)
    assert state.limit_state == 0
    assert state.q_pu == pytest.approx(0.0)

    vm = np.array([0.6, 1.0])
    update_svc_limits([state], vm)
    assert state.limit_state == 1
    assert state.q_pu == pytest.approx(1.0 * 0.6**2)

    vm = np.array([1.2, 1.0])
    update_svc_limits([state], vm)
    assert state.limit_state == -1
    assert state.q_pu == pytest.approx(-1.0 * 1.2**2)


def test_refresh_decoupled_svc_controls_updates_droop_injection() -> None:
    state = SVCState(
        device_index=0,
        bus_index=0,
        control_bus_index=1,
        active=True,
        mode="P",
        slope=0.05,
        q_pu=0.0,
        q_min_pu=-2.0,
        q_max_pu=2.0,
        v_ref=1.0,
    )
    vm = np.array([1.0, 1.04])
    refresh_decoupled_svc_controls([state], vm)
    assert state.q_pu == pytest.approx((1.0 - 1.04) / 0.05)

    state.mode = "I"
    refresh_decoupled_svc_controls([state], vm)
    assert state.q_pu == pytest.approx((1.0 - 1.04) * 1.0 / 0.05)

    state.slope = 0.0
    state.q_pu = 1.0
    refresh_decoupled_svc_controls([state], vm)
    assert state.q_pu == pytest.approx(1.0)


def test_svc_q_injection_by_bus_sums_active_states() -> None:
    states = [
        SVCState(0, 0, 0, True, "P", 0.01, 0.3, -1.0, 1.0, 1.0),
        SVCState(1, 2, 2, True, "P", 0.01, 0.4, -1.0, 1.0, 1.0),
        SVCState(2, 0, 0, False, "P", 0.01, 9.9, -1.0, 1.0, 1.0),
    ]
    injection = svc_q_injection_by_bus(states, 3)
    assert injection.tolist() == pytest.approx([0.3, 0.0, 0.4])


def test_sync_svc_states_to_case_updates_bus_generation() -> None:
    svc = SVCData(
        bus=1,
        controlled_bus=1,
        mode="P",
        slope=0.05,
        reactive_power=10.0,
        minimum_reactive_power=-100.0,
        maximum_reactive_power=100.0,
        reference_voltage=1.0,
    )
    bus = _bus(1, reactive_generation=10.0)
    case = _case([bus], svcs=[svc])
    state = SVCState(
        device_index=0,
        bus_index=0,
        control_bus_index=0,
        active=True,
        mode="P",
        slope=0.05,
        q_pu=0.5,
        q_min_pu=-1.0,
        q_max_pu=1.0,
        v_ref=1.0,
    )

    sync_svc_states_to_case(case, [state])

    assert svc.reactive_power == pytest.approx(50.0)
    assert bus.reactive_generation == pytest.approx(50.0)
    sync_svc_states_to_case(case, [state])
    assert bus.reactive_generation == pytest.approx(50.0)


def test_build_ybus_rejects_zero_impedance_branch() -> None:
    case = _case(
        [_bus(1), _bus(2)],
        branches=[_branch(1, 2, resistance=0.0, reactance=0.0)],
    )

    with pytest.raises(ValueError, match="zero impedance"):
        build_ybus(case)


def test_assign_island_reference_buses_promotes_isolated_island() -> None:
    case = _case(
        [
            _bus(1, kind=ACBusTypes.REF, active_generation=100.0),
            _bus(2, kind=ACBusTypes.PV, active_generation=50.0),
            _bus(3, active_generation=10.0),
            _bus(4, active_generation=20.0),
        ],
        branches=[_branch(1, 2), _branch(3, 4)],
    )

    assigned = assign_island_reference_buses(case, build_ybus(case))

    assert assigned == [4]
    assert case.buses[3].kind == ACBusTypes.SLACK
    assert case.buses[0].kind == ACBusTypes.REF


def _iteration(iteration: int) -> IterationPowerFlowResult:
    return IterationPowerFlowResult(
        iteration=iteration,
        max_dp=1e-3,
        max_dq=1e-4,
        max_control_residual=0.0,
        max_residual=1e-3,
        max_step=1e-5,
    )


def test_live_iteration_reporter_phase_transitions(capsys) -> None:
    reporter = LiveIterationReporter("fast-decoupled")
    reporter.start()
    reporter.begin_phase("Control pass 1: SVC")
    reporter.emit(_iteration(0))
    reporter.fail("Base solve")
    reporter.reject("Control pass 1: SVC")
    text = reporter.finish()

    assert "Control pass 1: SVC" in text
    assert "[Base solve did not converge]" in text
    assert "[Control pass 1: SVC rejected; previous converged solution restored]" in text
    assert "1.0000e-03" in text
    capsys.readouterr()


def test_format_power_flow_report_renders_iteration_trace() -> None:
    result = ACPowerFlowResult(
        solver="fast-decoupled",
        converged=True,
        diverged=False,
        iterations=1,
        max_mismatch=1e-3,
        base_mva=100.0,
        iteration_trace=[_iteration(0), _iteration(1)],
        buses=[],
        branches=[],
    )

    text = format_power_flow_report(result, print_iterations=True)
    assert "Iteration-by-iteration convergence trace (Fast-decoupled)" in text
    assert "1.0000e-03" in text
    assert format_power_flow_report(result, print_iterations=False) == ""


def test_apply_power_flow_result_skips_non_acbus_records() -> None:
    class _NotABus:
        number = 1

    parsed = ParsedAnaredeSystem(
        source=Path("fake.pwf"),
        system=AnaredeSystem(name="fake"),
        components_by_block={"DBAR": [_NotABus()]},
        component_classes={},
    )
    result = ACPowerFlowResult(
        solver="newton-raphson",
        converged=True,
        diverged=False,
        iterations=0,
        max_mismatch=0.0,
        base_mva=100.0,
        iteration_trace=[],
        buses=[
            BusPowerFlowResult(
                id=1,
                name="",
                voltage_pu=1.0,
                angle_rad=0.0,
                active_injection_pu=0.0,
                reactive_injection_pu=0.0,
            )
        ],
        branches=[],
    )

    apply_power_flow_result(parsed, result)


def test_integer_key_handles_blank_and_invalid_values() -> None:
    from o_grid.acpf.results import _integer_key

    assert _integer_key(None) == 0
    assert _integer_key("") == 0
    assert _integer_key("abc") == 0
    assert _integer_key("12.5") == 12


def test_power_flow_run_system_property() -> None:
    system = AnaredeSystem(name="run")
    parsed = ParsedAnaredeSystem(
        source=Path("fake.pwf"),
        system=system,
        components_by_block={},
        component_classes={},
    )
    result = ACPowerFlowResult(
        solver="newton-raphson",
        converged=True,
        diverged=False,
        iterations=0,
        max_mismatch=0.0,
        base_mva=100.0,
        iteration_trace=[],
        buses=[],
        branches=[],
    )

    from o_grid.acpf.results import PowerFlowRun

    run = PowerFlowRun(parsed=parsed, result=result, stdout="")
    assert run.system is system


class _BlockComponent:
    def __init__(self, values: dict) -> None:
        self.ext = {"pwf_values": values}


def _lcc_blocks() -> dict[str, list[object]]:
    return {
        "DCNV": [
            _BlockComponent(
                {
                    "dc_bus": 10,
                    "mode": "R",
                    "number": 100,
                    "ac_bus": 1,
                    "commutation_reactance": 12.0,
                    "secondary_voltage": 55.0,
                    "transformer_power": 250.0,
                    "six_pulse_bridges": 2,
                }
            ),
            _BlockComponent(
                {
                    "dc_bus": 20,
                    "mode": "I",
                    "number": 200,
                    "ac_bus": 2,
                    "commutation_reactance": 10.0,
                    "secondary_voltage": 55.0,
                    "transformer_power": 250.0,
                    "six_pulse_bridges": 2,
                }
            ),
        ],
        "DCCV": [
            _BlockComponent(
                {
                    "number": 100,
                    "slack": "F",
                    "converter_control_type": "C",
                    "specified_value": 500.0,
                    "converter_angle": 15.0,
                    "tap_reduced_voltage_mode": 1.0,
                }
            ),
            _BlockComponent(
                {
                    "number": 200,
                    "slack": "N",
                    "converter_control_type": "P",
                    "specified_value": 500.0,
                    "converter_angle": 18.0,
                    "tap_reduced_voltage_mode": 1.0,
                }
            ),
        ],
        "DCBA": [
            _BlockComponent({"number": 10, "dc_link_number": 1, "voltage": 250.0}),
            _BlockComponent({"number": 20, "dc_link_number": 1, "voltage": 250.0}),
        ],
        "DELO": [
            _BlockComponent(
                {"number": 1, "name": "Bipole 1", "voltage": 250.0, "power_base": 1000.0}
            )
        ],
        "DCLI": [_BlockComponent({"from_bus": 10, "to_bus": 20, "resistance": 1.0})],
    }


def test_build_lcc_data_builds_rectifier_slack_link() -> None:
    lccs = build_lcc_data(_lcc_blocks())

    assert len(lccs) == 1
    lcc = lccs[0]
    assert lcc.rectifier_slack is True
    assert lcc.inverter_slack is False
    assert lcc.rectifier_control_mode == "Slack"
    assert lcc.inverter_control_mode == "Power"
    assert lcc.rectifier_bus == 1
    assert lcc.inverter_bus == 2
    assert lcc.current_ka == pytest.approx(2.0)
    assert lcc.p_rectifier_mw == pytest.approx(504.0)
    assert lcc.p_inverter_mw == pytest.approx(500.0)
    assert lcc.vdc_rectifier_kv == pytest.approx(252.0)
    assert lcc.alpha_deg == pytest.approx(15.0)
    assert lcc.gamma_deg == pytest.approx(18.0)


def test_build_lcc_data_skips_link_with_missing_converter() -> None:
    blocks = _lcc_blocks()
    blocks["DCLI"] = [_BlockComponent({"from_bus": 10, "to_bus": 99, "resistance": 1.0})]

    assert build_lcc_data(blocks) == []


def test_build_lcc_data_skips_non_rectifier_inverter_pair() -> None:
    blocks = _lcc_blocks()
    blocks["DCNV"][0].ext["pwf_values"]["mode"] = "I"

    assert build_lcc_data(blocks) == []


def test_build_lcc_data_requires_exactly_one_slack_converter() -> None:
    blocks = _lcc_blocks()
    blocks["DCCV"][0].ext["pwf_values"]["slack"] = "N"
    blocks["DCCV"][1].ext["pwf_values"]["slack"] = "N"

    with pytest.raises(ValueError, match="exactly one DCCV slack converter"):
        build_lcc_data(blocks)


def test_build_lcc_data_requires_power_control_on_normal_converter() -> None:
    blocks = _lcc_blocks()
    blocks["DCCV"][1].ext["pwf_values"]["converter_control_type"] = "C"

    assert build_lcc_data(blocks) == []


def test_build_lcc_data_handles_blank_and_invalid_numeric_values() -> None:
    blocks = _lcc_blocks()
    blocks["DCCV"][0].ext["pwf_values"]["converter_angle"] = ""
    blocks["DCNV"][0].ext["pwf_values"]["six_pulse_bridges"] = "abc"
    blocks["DCNV"][0].ext["pwf_values"]["commutation_reactance"] = "bad"

    lccs = build_lcc_data(blocks)

    assert len(lccs) == 1
    assert lccs[0].alpha_deg == pytest.approx(0.0)
    assert lccs[0].rectifier_poles == 1
    assert lccs[0].xcr_percent == pytest.approx(0.0)


def test_build_lcc_injections_returns_terminal_injections() -> None:
    injections = build_lcc_injections(_lcc_blocks())

    assert len(injections) == 2
    assert injections[0].bus == 1
    assert injections[0].active_mw == pytest.approx(-504.0)
    assert injections[1].bus == 2
    assert injections[1].active_mw == pytest.approx(500.0)


def _lcc_data(rectifier_slack: bool = True) -> LCCData:
    return LCCData(
        link_id=1,
        link_name="Bipole 1",
        rectifier_bus=1,
        inverter_bus=2,
        pdc_mw=500.0,
        p_rectifier_mw=504.0,
        p_inverter_mw=500.0,
        q_rectifier_mvar=50.0,
        q_inverter_mvar=60.0,
        rdc_ohm=1.0,
        vdc_rectifier_kv=252.0,
        vdc_inverter_kv=250.0,
        rectifier_slack=rectifier_slack,
        inverter_slack=not rectifier_slack,
        rectifier_control_mode="Slack",
        inverter_control_mode="Power",
        alpha_deg=15.0,
        gamma_deg=18.0,
        xcr_percent=12.0,
        xci_percent=10.0,
        rectifier_bridge_voltage_kv=55.0,
        inverter_bridge_voltage_kv=55.0,
        rectifier_nominal_mva=250.0,
        inverter_nominal_mva=250.0,
        rectifier_poles=2,
        inverter_poles=2,
        tap_rectifier=1.0,
        tap_inverter=1.0,
        tap_rectifier_min=0.9,
        tap_rectifier_max=1.1,
        tap_inverter_min=0.9,
        tap_inverter_max=1.1,
        vbase_kv=250.0,
        power_base_mw=1000.0,
    )


def test_update_lcc_from_dc_solution_rectifier_slack() -> None:
    lcc = _lcc_data(rectifier_slack=True)
    case = _case(
        [_bus(1, active_load=0.0), _bus(2, active_generation=0.0)],
        lccs=[lcc],
    )

    changed = update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert bool(changed) is True
    assert lcc.p_rectifier_mw == pytest.approx(504.0)
    assert lcc.p_inverter_mw == pytest.approx(500.0)


def test_update_lcc_from_dc_solution_inverter_slack() -> None:
    lcc = _lcc_data(rectifier_slack=False)
    case = _case(
        [_bus(1, active_load=0.0), _bus(2, active_generation=0.0)],
        lccs=[lcc],
    )

    changed = update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert bool(changed) is True


def test_update_lcc_from_dc_solution_skips_zero_power_links() -> None:
    lcc = _lcc_data()
    lcc.pdc_mw = 0.0
    case = _case([_bus(1), _bus(2)], lccs=[lcc])

    changed = update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert changed is False


def test_update_lcc_from_dc_solution_low_voltage_link() -> None:
    lcc = _lcc_data()
    lcc.vbase_kv = 10.0
    case = _case([_bus(1), _bus(2)], lccs=[lcc])

    update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert lcc.q_rectifier_mvar == pytest.approx(50.0)
    assert lcc.q_inverter_mvar == pytest.approx(60.0)


def test_update_lcc_from_dc_solution_zero_bridge_voltage_target_tap() -> None:
    lcc = _lcc_data()
    lcc.rectifier_bridge_voltage_kv = 0.0
    lcc.inverter_bridge_voltage_kv = 0.0
    case = _case([_bus(1), _bus(2)], lccs=[lcc])

    update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert lcc.tap_rectifier == pytest.approx(1.0)
    assert lcc.tap_inverter == pytest.approx(1.0)


def test_update_lcc_from_dc_solution_zero_overlap_inputs_keeps_previous() -> None:
    lcc = _lcc_data()
    lcc.rectifier_nominal_mva = 0.0
    lcc.inverter_nominal_mva = 0.0
    case = _case([_bus(1), _bus(2)], lccs=[lcc])

    update_lcc_from_dc_solution(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))

    assert lcc.mu_rectifier_deg == pytest.approx(0.0)
    assert lcc.mu_inverter_deg == pytest.approx(0.0)


def test_refresh_lcc_reporting_state_skips_zero_power_links() -> None:
    lcc = _lcc_data()
    lcc.pdc_mw = 0.0
    case = _case([_bus(1), _bus(2)], lccs=[lcc])

    refresh_lcc_reporting_state(case, np.array([1.0 + 0.0j, 1.0 + 0.0j]))
