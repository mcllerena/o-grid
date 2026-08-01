"""Switched bus-shunt state and voltage-control updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from o_grid.acpf.models.case import PowerFlowCase


@dataclass(slots=True)
class ShuntControlData:
    bus: int
    controlled_bus: int
    reactive_power: float
    minimum_reactive_power: float
    maximum_reactive_power: float
    minimum_voltage: float
    maximum_voltage: float
    fixed: bool


def adjust_switched_shunts(case: PowerFlowCase, voltage: np.ndarray) -> bool:
    """Switch aggregate shunt-bank injection to its bounded voltage target."""
    indices = case.bus_index
    buses = {bus.number: bus for bus in case.buses}
    changed = False
    for shunt in case.shunt_controls or []:
        if shunt.fixed or shunt.maximum_voltage <= shunt.minimum_voltage:
            continue
        control_voltage = abs(voltage[indices[shunt.controlled_bus]])
        target = shunt.reactive_power
        if control_voltage > shunt.maximum_voltage + 1e-3:
            target = min(0.0, shunt.minimum_reactive_power)
        elif control_voltage < shunt.minimum_voltage - 1e-3:
            target = max(0.0, shunt.maximum_reactive_power)
        delta = target - shunt.reactive_power
        if abs(delta) <= 1e-3:
            continue
        buses[shunt.bus].shunt_susceptance += delta / case.base_mva
        shunt.reactive_power = target
        changed = True
    return changed
