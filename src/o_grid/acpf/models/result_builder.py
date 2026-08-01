"""Build infrasys result components from a solved numerical case."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import TypedDict

from o_grid.acpf.models.case import PowerFlowCase
from o_grid.acpf.models.lcc import LCCData
from o_grid.acpf.models.network_reduction import ReducedPowerFlowCase
from o_grid.acpf.models.results import (
    ACBusResults,
    ACLineResults,
    ControllableSeriesCompensatorResults,
    DCLineResults,
    GeneratorResults,
    LTCTransformerResults,
    PhaseShiftingTransformerResults,
    PowerFlowResults,
    StaticVARCompensatorResults,
    StatisticResultsInformation,
    SwitchDeviceResults,
    TransformerResults,
)
from o_grid.acpf.results import ACPowerFlowResult, BranchPowerFlowResult, BusPowerFlowResult
from o_grid.parser import ParsedAnaredeSystem
from o_grid.units import get_magnitude


class TerminalFlowValues(TypedDict):
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str


class LineFlowValues(TerminalFlowValues):
    loading_percent: float
    active_loss_mw: float
    reactive_loss_mvar: float


def build_component_results(
    parsed: ParsedAnaredeSystem,
    case: PowerFlowCase,
    result: ACPowerFlowResult,
    *,
    reduction: ReducedPowerFlowCase | None = None,
    tolerance: float = 1e-6,
) -> PowerFlowResults:
    """Construct workbook-aligned result components for the solved system."""
    solved_buses = {bus.id: bus for bus in result.buses}
    bus_data = {bus.number: bus for bus in case.buses}
    branch_results = {_branch_key(branch): branch for branch in result.branches}
    representative_buses = (
        reduction.representative_buses(case)
        if reduction is not None
        else {bus.number: bus.number for bus in case.buses}
    )

    ac_buses = []
    for component in parsed.components_by_block.get("DBAR", []):
        number = _number(getattr(component, "number", 0))
        solved = solved_buses[number]
        data = bus_data[number]
        base_voltage = _optional_magnitude(getattr(component, "base_voltage", None))
        voltage_kv = solved.voltage_pu * base_voltage if base_voltage is not None else None
        violation = None
        if solved.voltage_pu > data.maximum_voltage:
            violation = "upper"
        elif solved.voltage_pu < data.minimum_voltage:
            violation = "lower"
        ac_buses.append(
            ACBusResults(
                name=_result_name(component),
                bus_number=number,
                bus_name=data.name,
                bus_type=data.kind.value,
                area=_area_number(getattr(component, "area", None)),
                in_service=bool(getattr(component, "available", True)),
                voltage_pu=solved.voltage_pu,
                voltage_kv=voltage_kv,
                angle_deg=math.degrees(solved.angle_rad),
                active_generation_mw=(
                    solved.active_injection_pu * result.base_mva + data.active_load
                ),
                reactive_generation_mvar=(
                    solved.reactive_injection_pu * result.base_mva + data.reactive_load
                ),
                active_load_mw=data.active_load,
                reactive_load_mvar=data.reactive_load,
                minimum_voltage_pu=data.minimum_voltage,
                maximum_voltage_pu=data.maximum_voltage,
                violation=violation,
                representative_bus=representative_buses[number],
                collapsed=representative_buses[number] != number,
            )
        )

    derived_keys = {
        block: {
            _component_branch_key(component)
            for component in parsed.components_by_block.get(block, [])
        }
        for block in ("DLIN_TAP", "DLIN_PHASE_SHIFT", "DLIN_TRANSFORMER", "DLIN_SWITCH")
    }
    generators = _build_generator_results(parsed.components_by_block.get("DGER", []), ac_buses)
    ac_lines = []
    line_number = 0
    for component in parsed.components_by_block.get("DLIN", []):
        key = _component_branch_key(component)
        if any(key in derived_keys[block] for block in derived_keys):
            continue
        solved = branch_results.get(key)
        if solved is None:
            continue
        line_number += 1
        values = _pwf_values(component)
        ac_lines.append(
            ACLineResults(
                name=_result_name(component),
                line_number=line_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                resistance_pu=_magnitude(
                    getattr(component, "r", None), values.get("resistance", 0.0)
                )
                * 0.01,
                reactance_pu=_magnitude(getattr(component, "x", None), values.get("reactance", 0.0))
                * 0.01,
                charging_pu=float(values.get("susceptance") or 0.0) / result.base_mva,
                tap_pu=float(values.get("tap") or 1.0),
                phase_shift_deg=float(values.get("phase_shift") or 0.0),
                rating_mva=_magnitude(
                    getattr(component, "normal_capacity", None),
                    values.get("normal_capacity", 0.0),
                ),
                **_line_flow_values(solved),
                violation=solved.loading_percent > 100.0,
            )
        )

    ltc_transformers = _build_ltc_results(
        parsed.components_by_block.get("DLIN_TAP", []), branch_results, solved_buses
    )
    transformers = _build_transformer_results(
        parsed.components_by_block.get("DLIN_TRANSFORMER", []), branch_results
    )
    phase_shifting_transformers = _build_phase_shifting_results(
        parsed.components_by_block.get("DLIN_PHASE_SHIFT", []), branch_results
    )
    switch_devices = _build_switch_results(
        parsed.components_by_block.get("DLIN_SWITCH", []), branch_results
    )
    static_var_compensators = _build_svc_results(parsed, solved_buses)
    controllable_series_compensators = _build_csc_results(
        parsed.components_by_block.get("DCSC", []), branch_results
    )
    original_bus_names = {
        _number(getattr(component, "number", 0)): str(
            _pwf_values(component).get("name") or getattr(component, "name", "")
        )
        for component in parsed.components_by_block.get("DBAR", [])
    }
    dc_lines = _build_dc_results(case.lccs or [], ac_buses, original_bus_names)

    state_count = len(case.pv_indices) + 2 * len(case.pq_indices)
    scheduled_generation = sum(bus.active_generation for bus in case.buses)
    solved_generation = sum(bus.active_generation_mw for bus in ac_buses)
    total_load = sum(bus.active_load_mw for bus in ac_buses)
    branch_active_losses = sum(branch.active_loss_mw for branch in result.branches)
    information = StatisticResultsInformation(
        name=f"{result.solver}-results",
        source_path=str(parsed.source),
        solver=result.solver,
        solver_mode=_solver_mode(result.solver, result.fallback_used),
        converged=result.converged,
        diverged=result.diverged,
        iterations=result.iterations,
        max_mismatch_pu=result.max_mismatch,
        base_mva=result.base_mva,
        estimated_dense_matrix_memory_gb=state_count**2 * 8 / 1024**3,
        convergence_tolerance_pu=tolerance,
        divergence_voltage_minimum_pu=0.4,
        divergence_voltage_maximum_pu=2.0,
        near_zero_guard_tolerance=1e-12,
        scheduled_generation_mw=scheduled_generation,
        solved_generation_mw=solved_generation,
        total_load_mw=total_load,
        branch_active_losses_mw=branch_active_losses,
        power_balance_mw=solved_generation - total_load - branch_active_losses,
        bus_count=len(ac_buses),
        bus_count_after_reduction=(len(reduction.case.buses) if reduction else len(case.buses)),
        branch_count=len(case.branches),
        branch_count_after_reduction=(
            len(reduction.case.branches) if reduction else len(case.branches)
        ),
        ac_line_count=len(ac_lines),
        ltc_count=len(ltc_transformers),
        phase_shifting_transformer_count=len(phase_shifting_transformers),
        switch_count=len(switch_devices),
        dc_line_count=len(case.lccs or []),
        static_var_compensator_count=len(static_var_compensators),
        controllable_series_compensator_count=len(controllable_series_compensators),
        voltage_upper_violations=sum(
            bus.violation == "upper" and not bus.collapsed for bus in ac_buses
        ),
        voltage_lower_violations=sum(
            bus.violation == "lower" and not bus.collapsed for bus in ac_buses
        ),
        line_flow_overloads=sum(line.violation for line in ac_lines),
        iteration_trace=result.iteration_trace,
    )
    return PowerFlowResults(
        information=information,
        ac_buses=ac_buses,
        generators=generators,
        ac_lines=ac_lines,
        transformers=transformers,
        ltc_transformers=ltc_transformers,
        phase_shifting_transformers=phase_shifting_transformers,
        switch_devices=switch_devices,
        static_var_compensators=static_var_compensators,
        controllable_series_compensators=controllable_series_compensators,
        dc_lines=dc_lines,
    )


def _build_generator_results(
    components: Iterable[object], solved_buses: Iterable[ACBusResults]
) -> list[GeneratorResults]:
    buses = {bus.bus_number: bus for bus in solved_buses}
    results = []
    for component in components:
        bus_number = _number(getattr(component, "number", 0))
        solved = buses.get(bus_number)
        if solved is None:
            continue
        maximum = _optional_magnitude(getattr(component, "max_active_generation", None))
        generator_type = getattr(component, "gen_type", None)
        results.append(
            GeneratorResults(
                name=_result_name(component),
                bus_number=bus_number,
                bus_name=solved.bus_name,
                generator_type=str(getattr(generator_type, "value", generator_type or "Unknown")),
                active_generation_mw=solved.active_generation_mw,
                reactive_generation_mvar=solved.reactive_generation_mvar,
                maximum_active_generation_mw=maximum,
                reserve_mw=(maximum - solved.active_generation_mw if maximum is not None else None),
                voltage_pu=solved.voltage_pu,
                angle_deg=solved.angle_deg,
            )
        )
    if results:
        return results
    for solved in buses.values():
        if solved.bus_type.upper() not in {"PV", "REF", "SLACK", "REFERENCE"}:
            continue
        results.append(
            GeneratorResults(
                name=f"generator-{solved.bus_number}:power-flow",
                bus_number=solved.bus_number,
                bus_name=solved.bus_name,
                generator_type="Unknown",
                active_generation_mw=solved.active_generation_mw,
                reactive_generation_mvar=solved.reactive_generation_mvar,
                maximum_active_generation_mw=None,
                reserve_mw=None,
                voltage_pu=solved.voltage_pu,
                angle_deg=solved.angle_deg,
            )
        )
    return results


def _build_transformer_results(
    components: Iterable[object],
    branch_results: dict[tuple[int, int, int], BranchPowerFlowResult],
) -> list[TransformerResults]:
    results = []
    for device_number, component in enumerate(components, start=1):
        key = _component_branch_key(component)
        solved = branch_results.get(key)
        if solved is None:
            continue
        values = _pwf_values(component)
        results.append(
            TransformerResults(
                name=_result_name(component),
                device_number=device_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                resistance_pu=_magnitude(getattr(component, "r", None)) * 0.01,
                reactance_pu=_magnitude(getattr(component, "x", None)) * 0.01,
                tap_pu=_magnitude(getattr(component, "tap", None), 1.0),
                phase_shift_deg=float(values.get("phase_shift") or 0.0),
                rating_mva=_magnitude(getattr(component, "normal_capacity", None)),
                **_line_flow_values(solved),
                violation=solved.loading_percent > 100.0,
            )
        )
    return results


def _build_ltc_results(
    components: Iterable[object],
    branch_results: dict[tuple[int, int, int], BranchPowerFlowResult],
    solved_buses: Mapping[int, BusPowerFlowResult],
) -> list[LTCTransformerResults]:
    results = []
    for device_number, component in enumerate(components, start=1):
        key = _component_branch_key(component)
        solved = branch_results.get(key)
        if solved is None:
            continue
        controlled_bus = _optional_number(getattr(component, "controlled_bus", None))
        target = getattr(solved_buses.get(controlled_bus), "voltage_pu", None)
        results.append(
            LTCTransformerResults(
                name=_result_name(component),
                device_number=device_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                controlled_bus=controlled_bus,
                tap_pu=_magnitude(getattr(component, "tap", None), 1.0),
                minimum_tap_pu=_optional_magnitude(getattr(component, "tap_minimum", None)),
                maximum_tap_pu=_optional_magnitude(getattr(component, "tap_maximum", None)),
                target_voltage_pu=target,
                **_terminal_flow_values(solved),
            )
        )
    return results


def _build_phase_shifting_results(
    components: Iterable[object],
    branch_results: dict[tuple[int, int, int], BranchPowerFlowResult],
) -> list[PhaseShiftingTransformerResults]:
    results = []
    for device_number, component in enumerate(components, start=1):
        key = _component_branch_key(component)
        solved = branch_results.get(key)
        if solved is None:
            continue
        shift = float(_pwf_values(component).get("phase_shift") or 0.0)
        results.append(
            PhaseShiftingTransformerResults(
                name=_result_name(component),
                device_number=device_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                controlled_bus=_optional_number(getattr(component, "controlled_bus", None)),
                phase_shift_deg=shift,
                minimum_phase_shift_deg=shift,
                maximum_phase_shift_deg=shift,
                target_active_power_mw=None,
                **_terminal_flow_values(solved),
            )
        )
    return results


def _build_switch_results(
    components: Iterable[object],
    branch_results: dict[tuple[int, int, int], BranchPowerFlowResult],
) -> list[SwitchDeviceResults]:
    results = []
    for device_number, component in enumerate(components, start=1):
        key = _component_branch_key(component)
        solved = branch_results.get(key)
        if solved is None:
            continue
        results.append(
            SwitchDeviceResults(
                name=_result_name(component),
                device_number=device_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                **_line_flow_values(solved),
                status="InSvc" if getattr(component, "available", True) else "OutSvc",
            )
        )
    return results


def _build_svc_results(
    parsed: ParsedAnaredeSystem,
    solved_buses: Mapping[int, BusPowerFlowResult],
) -> list[StaticVARCompensatorResults]:
    bus_components = {
        _number(getattr(bus, "number", 0)): bus
        for bus in parsed.components_by_block.get("DBAR", [])
    }
    results = []
    for device_number, component in enumerate(parsed.components_by_block.get("DCER", []), start=1):
        values = _pwf_values(component)
        bus_number = _number(getattr(component, "bus", values.get("bus", 0)))
        controlled_bus = _optional_number(getattr(component, "controlled_bus", None))
        solved = solved_buses.get(bus_number)
        initial_reactive = _magnitude(
            getattr(component, "reactive_generation", None),
            values.get("reactive_generation", 0.0),
        )
        reactive = initial_reactive
        results.append(
            StaticVARCompensatorResults(
                name=_result_name(component),
                device_number=device_number,
                bus_number=bus_number,
                bus_name=str(getattr(bus_components.get(bus_number), "name", "")),
                controlled_bus=controlled_bus,
                mode=str(getattr(component, "control_mode", "")),
                voltage_pu=float(getattr(solved, "voltage_pu", 0.0)),
                reference_voltage_pu=float(
                    getattr(solved_buses.get(controlled_bus), "voltage_pu", 0.0)
                )
                if controlled_bus is not None
                else None,
                slope_percent=_optional_magnitude(getattr(component, "slope", None)),
                reactive_power_mvar=reactive,
                initial_reactive_power_mvar=initial_reactive,
                reactive_power_delta_mvar=reactive - initial_reactive,
                minimum_reactive_power_mvar=_optional_magnitude(
                    getattr(component, "min_reactive_generation", None)
                ),
                maximum_reactive_power_mvar=_optional_magnitude(
                    getattr(component, "max_reactive_generation", None)
                ),
                status="InSvc" if getattr(component, "available", True) else "OutSvc",
                equation_residual=None,
            )
        )
    return results


def _build_csc_results(
    components: Iterable[object],
    branch_results: dict[tuple[int, int, int], BranchPowerFlowResult],
) -> list[ControllableSeriesCompensatorResults]:
    results = []
    for device_number, component in enumerate(components, start=1):
        key = _component_branch_key(component, circuit_field="dcsc_circuit")
        solved = branch_results.get(key)
        if solved is None:
            continue
        results.append(
            ControllableSeriesCompensatorResults(
                name=_result_name(component),
                device_number=device_number,
                from_bus=key[0],
                to_bus=key[1],
                circuit=key[2],
                mode=str(getattr(component, "control_mode", "")),
                reactance_pu=_magnitude(getattr(component, "initial_reactance", None)) * 0.01,
                minimum_reactance_pu=_scaled_optional(
                    getattr(component, "min_reactance", None), 0.01
                ),
                maximum_reactance_pu=_scaled_optional(
                    getattr(component, "max_reactance", None), 0.01
                ),
                **_terminal_flow_values(solved),
                status="InSvc" if getattr(component, "available", True) else "OutSvc",
            )
        )
    return results


def _build_dc_results(
    lccs: Iterable[LCCData],
    solved_buses: Iterable[ACBusResults],
    original_bus_names: Mapping[int, str],
) -> list[DCLineResults]:
    buses = {bus.bus_number: bus for bus in solved_buses}
    results: list[DCLineResults] = []
    for link_index, lcc in enumerate(sorted(lccs, key=lambda item: item.link_id), start=1):
        active = abs(lcc.pdc_mw) > 1e-12
        current_ka = abs(lcc.current_ka) if active else 0.0
        current_a = current_ka * 1000.0
        base_current_ka = (
            lcc.power_base_mw / lcc.vbase_kv
            if lcc.power_base_mw > 1e-12 and lcc.vbase_kv > 1e-12
            else 0.0
        )
        current_pu = current_ka / base_current_ka if base_current_ka > 1e-12 else 0.0
        loss_mw = current_ka**2 * max(0.0, lcc.rdc_ohm)
        pole_number = _lcc_pole_number(lcc, link_index)
        status = "ON" if active else "OFF"
        rectifier = buses.get(lcc.rectifier_bus)
        inverter = buses.get(lcc.inverter_bus)
        results.append(
            DCLineResults(
                name=f"LCC-{lcc.link_id}-rectifier:power-flow",
                bus_number=lcc.rectifier_bus,
                bus_name=original_bus_names.get(
                    lcc.rectifier_bus, rectifier.bus_name if rectifier is not None else ""
                )
                or None,
                voltage_pu=(abs(lcc.vdc_rectifier_kv) / lcc.vbase_kv if active else 1.0),
                converter_type="Rectifier",
                pole_number=pole_number,
                control_mode=lcc.rectifier_control_mode,
                active_power_mw=lcc.p_rectifier_mw,
                reactive_power_mvar=lcc.q_rectifier_mvar,
                loss_mw=loss_mw,
                dc_voltage_kv=lcc.vdc_rectifier_kv,
                dc_current_pu=current_pu,
                dc_current_a=current_a,
                firing_angle_deg=lcc.alpha_deg,
                overlap_angle_deg=lcc.mu_rectifier_deg,
                power_factor_angle_deg=None,
                tap_pu=lcc.tap_rectifier if active else 1.0,
                status=status,
            )
        )
        results.append(
            DCLineResults(
                name=f"LCC-{lcc.link_id}-inverter:power-flow",
                bus_number=lcc.inverter_bus,
                bus_name=original_bus_names.get(
                    lcc.inverter_bus, inverter.bus_name if inverter is not None else ""
                )
                or None,
                voltage_pu=(abs(lcc.vdc_inverter_kv) / lcc.vbase_kv if active else 1.0),
                converter_type="Inverter",
                pole_number=pole_number,
                control_mode=lcc.inverter_control_mode,
                active_power_mw=-lcc.p_inverter_mw,
                reactive_power_mvar=lcc.q_inverter_mvar,
                loss_mw=loss_mw,
                dc_voltage_kv=lcc.vdc_inverter_kv,
                dc_current_pu=-current_pu,
                dc_current_a=-current_a,
                firing_angle_deg=lcc.gamma_deg,
                overlap_angle_deg=lcc.mu_inverter_deg,
                power_factor_angle_deg=None,
                tap_pu=lcc.tap_inverter if active else 1.0,
                status=status,
            )
        )
    return results


def _lcc_pole_number(lcc: LCCData, fallback: int) -> int:
    match = re.search(r"(\d+)\s*$", lcc.link_name)
    return int(match.group(1)) if match else fallback


def _terminal_flow_values(solved: BranchPowerFlowResult) -> TerminalFlowValues:
    return {
        "active_from_mw": solved.active_from_mw,
        "reactive_from_mvar": solved.reactive_from_mvar,
        "active_to_mw": solved.active_to_mw,
        "reactive_to_mvar": solved.reactive_to_mvar,
        "power_factor_from": _power_factor(solved.active_from_mw, solved.reactive_from_mvar),
        "reactive_type_from": _reactive_type(solved.active_from_mw, solved.reactive_from_mvar),
        "power_factor_to": _power_factor(solved.active_to_mw, solved.reactive_to_mvar),
        "reactive_type_to": _reactive_type(solved.active_to_mw, solved.reactive_to_mvar),
    }


def _power_factor(active_mw: float, reactive_mvar: float) -> float:
    if active_mw <= 1e-9:
        return 0.0
    apparent_mva = math.hypot(active_mw, reactive_mvar)
    return active_mw / apparent_mva if apparent_mva > 1e-12 else 0.0


def _reactive_type(active_mw: float, reactive_mvar: float) -> str:
    if active_mw <= 1e-9:
        return "-"
    if reactive_mvar > 1e-9:
        return "Cap"
    if reactive_mvar < -1e-9:
        return "Ind"
    return "-"


def _line_flow_values(solved: BranchPowerFlowResult) -> LineFlowValues:
    return {
        **_terminal_flow_values(solved),
        "loading_percent": solved.loading_percent,
        "active_loss_mw": solved.active_loss_mw,
        "reactive_loss_mvar": solved.reactive_loss_mvar,
    }


def _branch_key(branch: BranchPowerFlowResult) -> tuple[int, int, int]:
    return branch.from_bus, branch.to_bus, branch.circuit


def _component_branch_key(
    component: object, circuit_field: str = "line_circuit"
) -> tuple[int, int, int]:
    values = _pwf_values(component)
    return (
        _number(getattr(component, "from_bus", values.get("from_bus", 0))),
        _number(getattr(component, "to_bus", values.get("to_bus", 0))),
        int(
            float(
                getattr(component, circuit_field, None)
                or values.get(circuit_field)
                or values.get("circuit")
                or 1
            )
        ),
    )


def _result_name(component: object) -> str:
    return f"{getattr(component, 'name', type(component).__name__)}:power-flow"


def _area_number(area: object) -> int | str | None:
    value = getattr(area, "area_number", area)
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return str(value)


def _number(value: object) -> int:
    return int(float(str(getattr(value, "number", value))))


def _optional_number(value: object) -> int | None:
    if value in (None, ""):
        return None
    return _number(value)


def _magnitude(value: object, default: object = 0.0) -> float:
    return float(get_magnitude(value if value is not None else default))


def _optional_magnitude(value: object) -> float | None:
    if value is None:
        return None
    try:
        return _magnitude(value)
    except (TypeError, ValueError):
        return None


def _scaled_optional(value: object, scale: float) -> float | None:
    magnitude = _optional_magnitude(value)
    return None if magnitude is None else magnitude * scale


def _pwf_values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}


def _solver_mode(solver: str, fallback_used: bool = False) -> str:
    if solver == "newton-raphson":
        return "sparse direct full Newton solve"
    if solver == "fast-decoupled":
        if fallback_used:
            return "sparse fast-decoupled solve with Newton-Raphson fallback"
        return "sparse factorized fast-decoupled solve"
    return solver
