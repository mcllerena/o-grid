"""Line-commutated converter state built from linked PWF DC records."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from o_grid.acpf.models.case import PowerFlowCase


@dataclass(slots=True)
class LCCData:
    link_id: int
    link_name: str
    rectifier_bus: int
    inverter_bus: int
    pdc_mw: float
    p_rectifier_mw: float
    p_inverter_mw: float
    q_rectifier_mvar: float
    q_inverter_mvar: float
    rdc_ohm: float
    vdc_rectifier_kv: float
    vdc_inverter_kv: float
    rectifier_slack: bool
    inverter_slack: bool
    rectifier_control_mode: str
    inverter_control_mode: str
    alpha_deg: float
    gamma_deg: float
    xcr_percent: float
    xci_percent: float
    rectifier_bridge_voltage_kv: float
    inverter_bridge_voltage_kv: float
    rectifier_nominal_mva: float
    inverter_nominal_mva: float
    rectifier_poles: int
    inverter_poles: int
    tap_rectifier: float
    tap_inverter: float
    tap_rectifier_min: float
    tap_rectifier_max: float
    tap_inverter_min: float
    tap_inverter_max: float
    vbase_kv: float
    power_base_mw: float
    mu_rectifier_deg: float = 0.0
    mu_inverter_deg: float = 0.0

    @property
    def current_ka(self) -> float:
        reference_voltage = self.vdc_inverter_kv if self.rectifier_slack else self.vdc_rectifier_kv
        return self.pdc_mw / reference_voltage if reference_voltage > 1e-12 else 0.0


@dataclass(slots=True)
class LCCInjection:
    bus: int
    active_mw: float
    reactive_mvar: float


def build_lcc_data(
    components_by_block: Mapping[str, Sequence[object]],
) -> list[LCCData]:
    """Pair DC converters through DCLI records and initialize their AC interface state."""
    converters = {
        int(_values(component).get("dc_bus") or 0): _values(component)
        for component in components_by_block.get("DCNV", [])
    }
    controls = {
        int(_values(component).get("number") or 0): _values(component)
        for component in components_by_block.get("DCCV", [])
    }
    dc_buses = {
        int(_values(component).get("number") or 0): _values(component)
        for component in components_by_block.get("DCBA", [])
    }
    links = {
        int(_values(component).get("number") or 0): _values(component)
        for component in components_by_block.get("DELO", [])
    }
    result: list[LCCData] = []
    for line_component in components_by_block.get("DCLI", []):
        line = _values(line_component)
        first = converters.get(int(line.get("from_bus") or 0))
        second = converters.get(int(line.get("to_bus") or 0))
        if first is None or second is None:
            continue
        rectifier, inverter = (
            (first, second) if str(first.get("mode")).upper() == "R" else (second, first)
        )
        if str(rectifier.get("mode")).upper() != "R" or str(inverter.get("mode")).upper() != "I":
            continue
        rectifier_control = controls.get(int(rectifier.get("number") or 0), {})
        inverter_control = controls.get(int(inverter.get("number") or 0), {})
        rectifier_slack = str(rectifier_control.get("slack") or "N").upper() == "F"
        inverter_slack = str(inverter_control.get("slack") or "N").upper() == "F"
        if rectifier_slack == inverter_slack:
            raise ValueError(
                "Each DCLI pole must have exactly one DCCV slack converter; "
                f"converters {rectifier.get('number')} and {inverter.get('number')} do not"
            )
        normal_control = rectifier_control if not rectifier_slack else inverter_control
        if str(normal_control.get("converter_control_type") or "").upper() != "P":
            continue
        rectifier_dc_bus = dc_buses.get(int(rectifier.get("dc_bus") or 0), {})
        inverter_dc_bus = dc_buses.get(int(inverter.get("dc_bus") or 0), {})
        link = links.get(int(rectifier_dc_bus.get("dc_link_number") or 0), {})
        pdc = abs(_number(normal_control.get("specified_value")))
        vdc_rectifier = abs(_number(rectifier_dc_bus.get("voltage"), _number(link.get("voltage"))))
        rdc = max(0.0, _number(line.get("resistance")))
        vdc_inverter = abs(_number(inverter_dc_bus.get("voltage"), vdc_rectifier))
        if rectifier_slack:
            current_ka = pdc / vdc_inverter if vdc_inverter > 1e-12 else 0.0
            p_rectifier = pdc + current_ka**2 * rdc
            vdc_rectifier = vdc_inverter + current_ka * rdc
            p_inverter = pdc
        else:
            current_ka = pdc / vdc_rectifier if vdc_rectifier > 1e-12 else 0.0
            p_rectifier = pdc
            p_inverter = max(0.0, pdc - current_ka**2 * rdc)
            vdc_inverter = max(0.0, vdc_rectifier - current_ka * rdc)
        alpha = _number(rectifier_control.get("converter_angle"))
        gamma = _number(inverter_control.get("converter_angle"))
        result.append(
            LCCData(
                link_id=int(_number(link.get("number"), len(result) + 1)),
                link_name=str(link.get("name") or ""),
                rectifier_bus=int(rectifier.get("ac_bus") or 0),
                inverter_bus=int(inverter.get("ac_bus") or 0),
                pdc_mw=pdc,
                p_rectifier_mw=p_rectifier,
                p_inverter_mw=p_inverter,
                q_rectifier_mvar=pdc * math.tan(math.radians(alpha)),
                q_inverter_mvar=p_inverter * math.tan(math.radians(gamma)),
                rdc_ohm=rdc,
                vdc_rectifier_kv=vdc_rectifier,
                vdc_inverter_kv=vdc_inverter,
                rectifier_slack=rectifier_slack,
                inverter_slack=inverter_slack,
                rectifier_control_mode=_control_mode(rectifier_control, rectifier_slack),
                inverter_control_mode=_control_mode(inverter_control, inverter_slack),
                alpha_deg=alpha,
                gamma_deg=gamma,
                xcr_percent=_number(rectifier.get("commutation_reactance")),
                xci_percent=_number(inverter.get("commutation_reactance")),
                rectifier_bridge_voltage_kv=_number(rectifier.get("secondary_voltage")),
                inverter_bridge_voltage_kv=_number(inverter.get("secondary_voltage")),
                rectifier_nominal_mva=_number(rectifier.get("transformer_power")),
                inverter_nominal_mva=_number(inverter.get("transformer_power")),
                rectifier_poles=max(1, int(_number(rectifier.get("six_pulse_bridges"), 1.0))),
                inverter_poles=max(1, int(_number(inverter.get("six_pulse_bridges"), 1.0))),
                tap_rectifier=_number(rectifier_control.get("tap_reduced_voltage_mode"), 1.0),
                tap_inverter=_number(inverter_control.get("tap_reduced_voltage_mode"), 1.0),
                tap_rectifier_min=_number(rectifier_control.get("minimum_transformer_tap")),
                tap_rectifier_max=_number(rectifier_control.get("maximum_transformer_tap")),
                tap_inverter_min=_number(inverter_control.get("minimum_transformer_tap")),
                tap_inverter_max=_number(inverter_control.get("maximum_transformer_tap")),
                vbase_kv=_number(link.get("voltage"), vdc_rectifier or 1.0),
                power_base_mw=_number(link.get("power_base")),
            )
        )
    return result


def build_lcc_injections(
    components_by_block: Mapping[str, Sequence[object]],
) -> list[LCCInjection]:
    """Return terminal injections for compatibility with component result construction."""
    injections: list[LCCInjection] = []
    for lcc in build_lcc_data(components_by_block):
        injections.extend(
            (
                LCCInjection(lcc.rectifier_bus, -lcc.p_rectifier_mw, -lcc.q_rectifier_mvar),
                LCCInjection(lcc.inverter_bus, lcc.p_inverter_mw, -lcc.q_inverter_mvar),
            )
        )
    return injections


def _values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}


def _number(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _control_mode(control: Mapping[str, object], slack: bool) -> str:
    if slack:
        return "Slack"
    return {"C": "Current", "P": "Power"}.get(
        str(control.get("converter_control_type") or "").upper(), "-"
    )


def _dc_operating_point(lcc: LCCData) -> tuple[float, float, float, float, float]:
    """Return current, terminal powers, and voltages with DCCV Folga balancing losses."""
    resistance = max(0.0, lcc.rdc_ohm)
    current_ka = lcc.current_ka
    if lcc.rectifier_slack:
        inverter_voltage = lcc.vdc_inverter_kv
        loss_mw = current_ka**2 * resistance
        return (
            current_ka,
            lcc.pdc_mw + loss_mw,
            lcc.pdc_mw,
            inverter_voltage + current_ka * resistance,
            inverter_voltage,
        )
    rectifier_voltage = lcc.vdc_rectifier_kv
    loss_mw = current_ka**2 * resistance
    return (
        current_ka,
        lcc.pdc_mw,
        max(0.0, lcc.pdc_mw - loss_mw),
        rectifier_voltage,
        max(0.0, rectifier_voltage - current_ka * resistance),
    )


def update_lcc_from_dc_solution(
    case: PowerFlowCase,
    voltage: np.ndarray,
    *,
    damping: float = 0.3,
    active_tolerance_mw: float = 0.1,
    reactive_tolerance_mvar: float = 0.1,
) -> bool:
    """Update LCC terminal injections, overlap angles, and taps from solved AC voltage."""
    if not case.lccs:
        return False
    indices = case.bus_index
    buses = {bus.number: bus for bus in case.buses}
    maximum_active_change = 0.0
    maximum_reactive_change = 0.0

    for lcc in case.lccs:
        if lcc.pdc_mw <= 1e-12:
            continue
        current_ka, target_p_rectifier, target_p_inverter, vdc_rectifier, vdc_inverter = (
            _dc_operating_point(lcc)
        )
        dc_loss_mw = current_ka**2 * max(0.0, lcc.rdc_ohm)
        lcc.vdc_rectifier_kv = vdc_rectifier
        lcc.vdc_inverter_kv = vdc_inverter
        next_p_rectifier = _damped(lcc.p_rectifier_mw, target_p_rectifier, damping)
        next_p_inverter = _damped(lcc.p_inverter_mw, target_p_inverter, damping)

        rectifier_voltage = abs(voltage[indices[lcc.rectifier_bus]])
        inverter_voltage = abs(voltage[indices[lcc.inverter_bus]])
        low_voltage = lcc.vbase_kv <= 10.0
        if low_voltage:
            target_q_rectifier = lcc.q_rectifier_mvar
            target_q_inverter = lcc.q_inverter_mvar
        else:
            rectifier_power = (
                lcc.pdc_mw + dc_loss_mw if 200.0 <= lcc.vbase_kv < 750.0 else lcc.pdc_mw
            )
            target_q_rectifier = _reactive_power(
                rectifier_power, lcc.alpha_deg, lcc.mu_rectifier_deg
            )
            target_q_inverter = _reactive_power(lcc.pdc_mw, lcc.gamma_deg, lcc.mu_inverter_deg)
        next_q_rectifier = _damped(lcc.q_rectifier_mvar, target_q_rectifier, damping)
        next_q_inverter = _damped(lcc.q_inverter_mvar, target_q_inverter, damping)

        next_tap_rectifier = _clamp_tap(
            _damped(
                lcc.tap_rectifier,
                _target_tap(
                    lcc.pdc_mw,
                    lcc.vdc_rectifier_kv,
                    lcc.alpha_deg,
                    lcc.mu_rectifier_deg,
                    lcc.rectifier_bridge_voltage_kv,
                    lcc.rectifier_poles,
                    1.0 if low_voltage else rectifier_voltage,
                    lcc.tap_rectifier_min,
                    lcc.tap_rectifier_max,
                ),
                damping,
            ),
            lcc.tap_rectifier_min,
            lcc.tap_rectifier_max,
        )
        next_tap_inverter = _clamp_tap(
            _damped(
                lcc.tap_inverter,
                _target_tap(
                    lcc.pdc_mw,
                    lcc.vdc_inverter_kv,
                    lcc.gamma_deg,
                    lcc.mu_inverter_deg,
                    lcc.inverter_bridge_voltage_kv,
                    lcc.inverter_poles,
                    1.0 if low_voltage else inverter_voltage,
                    lcc.tap_inverter_min,
                    lcc.tap_inverter_max,
                ),
                damping,
            ),
            lcc.tap_inverter_min,
            lcc.tap_inverter_max,
        )

        rectifier = buses[lcc.rectifier_bus]
        inverter = buses[lcc.inverter_bus]
        rectifier.active_load += next_p_rectifier - lcc.p_rectifier_mw
        rectifier.reactive_load += next_q_rectifier - lcc.q_rectifier_mvar
        inverter.active_generation += next_p_inverter - lcc.p_inverter_mw
        inverter.reactive_load += next_q_inverter - lcc.q_inverter_mvar
        maximum_active_change = max(
            maximum_active_change,
            abs(next_p_rectifier - lcc.p_rectifier_mw),
            abs(next_p_inverter - lcc.p_inverter_mw),
        )
        maximum_reactive_change = max(
            maximum_reactive_change,
            abs(next_q_rectifier - lcc.q_rectifier_mvar),
            abs(next_q_inverter - lcc.q_inverter_mvar),
        )
        lcc.p_rectifier_mw = next_p_rectifier
        lcc.p_inverter_mw = next_p_inverter
        lcc.q_rectifier_mvar = next_q_rectifier
        lcc.q_inverter_mvar = next_q_inverter
        lcc.tap_rectifier = next_tap_rectifier
        lcc.tap_inverter = next_tap_inverter
        lcc.mu_rectifier_deg = _overlap_angle(lcc, True, rectifier_voltage)
        lcc.mu_inverter_deg = _overlap_angle(lcc, False, inverter_voltage)

    return (
        maximum_active_change > active_tolerance_mw
        or maximum_reactive_change > reactive_tolerance_mvar
    )


def refresh_lcc_reporting_state(case: PowerFlowCase, voltage: np.ndarray) -> None:
    """Derive LCC reporting values from the final accepted AC solution."""
    if not case.lccs:
        return
    indices = case.bus_index
    for lcc in case.lccs:
        if lcc.pdc_mw <= 1e-12:
            continue
        _, _, _, lcc.vdc_rectifier_kv, lcc.vdc_inverter_kv = _dc_operating_point(lcc)
        lcc.mu_rectifier_deg = _overlap_angle(lcc, True, abs(voltage[indices[lcc.rectifier_bus]]))
        lcc.mu_inverter_deg = _overlap_angle(lcc, False, abs(voltage[indices[lcc.inverter_bus]]))


def _damped(current: float, target: float, damping: float) -> float:
    return (1.0 - damping) * current + damping * target


def _reactive_power(power_mw: float, angle_deg: float, overlap_deg: float) -> float:
    return abs(power_mw) * np.tan(np.deg2rad(angle_deg + 0.5 * overlap_deg))


def _clamp_tap(tap: float, minimum: float, maximum: float) -> float:
    return float(np.clip(tap, minimum, maximum)) if minimum > 0.0 and maximum > minimum else tap


def _target_tap(
    power_mw: float,
    dc_voltage_kv: float,
    angle_deg: float,
    overlap_deg: float,
    bridge_voltage_kv: float,
    poles: int,
    ac_voltage_pu: float,
    minimum: float,
    maximum: float,
) -> float:
    if min(power_mw, dc_voltage_kv, bridge_voltage_kv, ac_voltage_pu) <= 1e-12:
        return 1.0
    open_voltage = 0.995 * 3.0 * np.sqrt(2.0) / np.pi
    open_voltage *= max(1, poles) * bridge_voltage_kv * ac_voltage_pu
    tap = open_voltage * np.cos(np.deg2rad(angle_deg + 0.5 * overlap_deg)) / dc_voltage_kv
    return _clamp_tap(max(0.0, float(tap)), minimum, maximum)


def _overlap_angle(lcc: LCCData, rectifier: bool, ac_voltage_pu: float) -> float:
    dc_voltage = lcc.vdc_rectifier_kv if rectifier else lcc.vdc_inverter_kv
    reactance = lcc.xcr_percent if rectifier else lcc.xci_percent
    bridge_voltage = (
        lcc.rectifier_bridge_voltage_kv if rectifier else lcc.inverter_bridge_voltage_kv
    )
    nominal_mva = lcc.rectifier_nominal_mva if rectifier else lcc.inverter_nominal_mva
    tap = lcc.tap_rectifier if rectifier else lcc.tap_inverter
    angle_deg = lcc.alpha_deg if rectifier else lcc.gamma_deg
    previous = lcc.mu_rectifier_deg if rectifier else lcc.mu_inverter_deg
    if min(dc_voltage, reactance, bridge_voltage, nominal_mva, tap, ac_voltage_pu) <= 1e-12:
        return previous
    transformer_x_ohm = reactance * 0.01 * bridge_voltage**2 / nominal_mva
    current_ka = lcc.current_ka
    terminal_voltage = tap * bridge_voltage * ac_voltage_pu
    argument = np.cos(np.deg2rad(angle_deg))
    argument -= np.sqrt(2.0) * transformer_x_ohm * current_ka / terminal_voltage
    return max(
        0.0,
        float(np.rad2deg(np.arccos(np.clip(argument, -1.0, 1.0))) - angle_deg),
    )
