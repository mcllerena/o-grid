"""Static VAR compensator state and voltage-control updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from o_grid.models import ACBusTypes

if TYPE_CHECKING:
    from o_grid.acpf.models.case import PowerFlowCase


@dataclass(slots=True)
class SVCData:
    bus: int
    controlled_bus: int
    mode: str
    slope: float
    reactive_power: float
    minimum_reactive_power: float
    maximum_reactive_power: float
    reference_voltage: float


@dataclass(slots=True)
class SVCState:
    """Numerical SVC control state mirroring the C++ reference formulation."""

    device_index: int
    bus_index: int
    control_bus_index: int
    active: bool
    mode: str
    slope: float
    q_pu: float
    q_min_pu: float
    q_max_pu: float
    v_ref: float
    limit_state: int = 0
    control_residual: float = 0.0


def build_svc_states(case: PowerFlowCase, voltage: np.ndarray) -> list[SVCState]:
    """Build SVC states for buses solved as PQ, matching the reference DCER model."""
    indices = case.bus_index
    states = []
    for device_index, svc in enumerate(case.svcs or []):
        bus_index = indices[svc.bus]
        control_index = indices[svc.controlled_bus]
        active = case.buses[bus_index].kind == ACBusTypes.PQ
        states.append(
            SVCState(
                device_index=device_index,
                bus_index=bus_index,
                control_bus_index=control_index,
                active=active,
                mode=svc.mode.upper(),
                slope=svc.slope,
                q_pu=svc.reactive_power / case.base_mva if active else 0.0,
                q_min_pu=svc.minimum_reactive_power / case.base_mva,
                q_max_pu=svc.maximum_reactive_power / case.base_mva,
                v_ref=svc.reference_voltage,
            )
        )
    update_svc_limits(states, np.abs(voltage))
    return states


def update_svc_limits(states: list[SVCState], vm: np.ndarray) -> None:
    """Refresh SVC limits, clamp the injection, and recompute control residuals."""
    for state in states:
        state.limit_state = 0
        if not state.active:
            state.q_pu = 0.0
            state.control_residual = 0.0
            continue
        control_voltage = float(vm[state.control_bus_index])
        squared = control_voltage * control_voltage
        lower = state.q_min_pu * squared
        upper = state.q_max_pu * squared
        control_q = state.q_pu
        if abs(state.slope) > 1e-12:
            if state.mode == "I":
                control_q = (state.v_ref - control_voltage) * vm[state.bus_index] / state.slope
            else:
                control_q = (state.v_ref - control_voltage) / state.slope
        if control_q < lower:
            state.q_pu = lower
            state.limit_state = -1
        elif control_q > upper:
            state.q_pu = upper
            state.limit_state = 1
        state.control_residual = svc_control_residual(state, vm)


def svc_control_residual(state: SVCState, vm: np.ndarray) -> float:
    """Return the SVC control/limit residual included in the Newton mismatch vector."""
    if not state.active:
        return 0.0
    control_voltage = float(vm[state.control_bus_index])
    if state.limit_state == -1:
        return state.q_min_pu * control_voltage * control_voltage - state.q_pu
    if state.limit_state == 1:
        return state.q_max_pu * control_voltage * control_voltage - state.q_pu
    if state.mode == "I":
        return control_voltage - state.v_ref + state.q_pu * state.slope / control_voltage
    return control_voltage - state.v_ref + state.q_pu * state.slope


def svc_control_derivative_voltage(state: SVCState, bus_index: int, vm: np.ndarray) -> float:
    """Return the SVC residual derivative with respect to a bus voltage magnitude."""
    if not state.active:
        return 0.0
    derivative = 0.0
    if state.limit_state == -1:
        if bus_index == state.control_bus_index:
            derivative += 2.0 * state.q_min_pu * vm[state.control_bus_index]
    elif state.limit_state == 1:
        if bus_index == state.control_bus_index:
            derivative += 2.0 * state.q_max_pu * vm[state.control_bus_index]
    else:
        if bus_index == state.control_bus_index:
            derivative += 1.0
        if state.mode == "I" and bus_index == state.bus_index:
            device_voltage = max(float(vm[state.bus_index]), 1e-12)
            derivative -= state.q_pu * state.slope / (device_voltage * device_voltage)
    return derivative


def svc_control_derivative_q(state: SVCState, vm: np.ndarray) -> float:
    """Return the SVC residual derivative with respect to its reactive-power state."""
    if not state.active:
        return 0.0
    if state.limit_state != 0:
        return -1.0
    if state.mode == "I":
        return state.slope / max(float(vm[state.bus_index]), 1e-12)
    return state.slope


def svc_q_injection_by_bus(states: list[SVCState], bus_count: int) -> np.ndarray:
    """Return per-unit SVC reactive injections summed by bus for active states."""
    injection = np.zeros(bus_count, dtype=float)
    for state in states:
        if state.active:
            injection[state.bus_index] += state.q_pu
    return injection


def refresh_decoupled_svc_controls(states: list[SVCState], vm: np.ndarray) -> None:
    """Refresh SVC injections from droop equations and limits inside FD iterations."""
    for state in states:
        if not state.active or abs(state.slope) <= 1e-12:
            continue
        if state.mode == "I":
            state.q_pu = (
                (state.v_ref - vm[state.control_bus_index]) * vm[state.bus_index] / state.slope
            )
        else:
            state.q_pu = (state.v_ref - vm[state.control_bus_index]) / state.slope
    update_svc_limits(states, vm)


def clamp_svc_seed_to_limits(case: PowerFlowCase) -> bool:
    """Clamp active SVC seed injections to their physical reactive band.

    The ANAREDE snapshot can schedule an SVC beyond its reactive capability
    (e.g. a saturated device whose raw seed injection exceeds the DCER band).
    The bus generation is adjusted by the same delta so the specified reactive
    balance at the bus is unchanged while the seed becomes self-consistent with
    the SVC limits used by the optimization and warm-start paths.
    """
    buses = {bus.number: bus for bus in case.buses}
    changed = False
    for svc in case.svcs or []:
        bus = buses.get(svc.bus)
        if bus is None or bus.kind != ACBusTypes.PQ:
            continue
        minimum = float(svc.minimum_reactive_power or 0.0)
        maximum = float(svc.maximum_reactive_power or 0.0)
        if not minimum and not maximum:
            continue
        clamped = min(max(svc.reactive_power, minimum), maximum)
        delta = clamped - svc.reactive_power
        if abs(delta) <= 1e-12:
            continue
        svc.reactive_power = clamped
        bus.reactive_generation += delta
        changed = True
    return changed


def sync_svc_states_to_case(case: PowerFlowCase, states: list[SVCState]) -> None:
    """Copy solved SVC injections back to the case so results and re-solves see them."""
    if not states:
        return
    buses = {bus.number: bus for bus in case.buses}
    svcs = case.svcs or []
    for state in states:
        if not state.active:
            continue
        solved_q = state.q_pu * case.base_mva
        svc = svcs[state.device_index]
        delta = solved_q - svc.reactive_power
        if abs(delta) <= 1e-12:
            continue
        svc.reactive_power = solved_q
        buses[case.buses[state.bus_index].number].reactive_generation += delta


def adjust_svc_reactive_power(case: PowerFlowCase, voltage: np.ndarray) -> bool:
    """Update active PQ-bus SVC injections from their droop equations and limits."""
    indices = case.bus_index
    buses = {bus.number: bus for bus in case.buses}
    changed = False
    for svc in case.svcs or []:
        if buses[svc.bus].kind != ACBusTypes.PQ or abs(svc.slope) <= 1e-12:
            continue
        control_voltage = abs(voltage[indices[svc.controlled_bus]])
        device_voltage = abs(voltage[indices[svc.bus]])
        target_pu = (svc.reference_voltage - control_voltage) / svc.slope
        if svc.mode.upper().endswith("I"):
            target_pu *= device_voltage
        minimum = svc.minimum_reactive_power * control_voltage**2
        maximum = svc.maximum_reactive_power * control_voltage**2
        target = float(np.clip(target_pu * case.base_mva, minimum, maximum))
        delta = target - svc.reactive_power
        if abs(delta) <= 1e-3:
            continue
        buses[svc.bus].reactive_generation += delta
        svc.reactive_power = target
        changed = True
    return changed


def active_svc_injection_by_bus(case: PowerFlowCase) -> dict[int, float]:
    """Return reactive injections for SVCs active in the C++ PQ-bus formulation."""
    buses = {bus.number: bus for bus in case.buses}
    reactive_power: dict[int, float] = {}
    for svc in case.svcs or []:
        if buses[svc.bus].kind == ACBusTypes.PQ:
            reactive_power[svc.bus] = reactive_power.get(svc.bus, 0.0) + svc.reactive_power
    return reactive_power
