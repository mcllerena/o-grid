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
