"""Voltage-control updates for SVCs, switched shunts, and LTC transformers."""

from __future__ import annotations

import numpy as np
from scipy.sparse import csc_matrix

from o_grid.acpf.models import PowerFlowCase, PowerFlowSettings
from o_grid.acpf.models.svc import active_svc_injection_by_bus
from o_grid.acpf.utils.network import calculate_power
from o_grid.models import ACBusTypes


def apply_bus_limit_controls(
    case: PowerFlowCase,
    ybus: csc_matrix,
    voltage: np.ndarray,
    settings: PowerFlowSettings,
) -> tuple[bool, np.ndarray]:
    """Apply irreversible QLIM and VLIM bus-type conversions used by the C++ solver."""
    changed = False
    calculated = calculate_power(ybus, voltage)
    svc_reactive_power = active_svc_injection_by_bus(case)

    if settings.enabled("QLIM"):
        for index, bus in enumerate(case.buses):
            if (
                bus.kind != ACBusTypes.PV
                or bus.minimum_reactive_generation is None
                or bus.maximum_reactive_generation is None
            ):
                continue
            required = (
                calculated[index].imag * case.base_mva
                + bus.reactive_load
                - svc_reactive_power.get(bus.number, 0.0)
            )
            if required > bus.maximum_reactive_generation + 0.1:
                bus.reactive_generation = bus.maximum_reactive_generation
                bus.kind = ACBusTypes.PQ
                changed = True
            elif required < bus.minimum_reactive_generation - 0.1:
                bus.reactive_generation = bus.minimum_reactive_generation
                bus.kind = ACBusTypes.PQ
                changed = True

    if settings.enabled("VLIM"):
        magnitude = np.abs(voltage)
        angle = np.angle(voltage)
        for index, bus in enumerate(case.buses):
            if bus.kind != ACBusTypes.PQ or bus.maximum_voltage <= bus.minimum_voltage:
                continue
            target = None
            if magnitude[index] > bus.maximum_voltage + settings.control_tolerance:
                target = bus.maximum_voltage
            elif magnitude[index] < bus.minimum_voltage - settings.control_tolerance:
                target = bus.minimum_voltage
            if target is not None:
                magnitude[index] = target
                bus.voltage = target
                bus.kind = ACBusTypes.PV
                changed = True

        if changed:
            voltage = magnitude * np.exp(1j * angle)
    return changed, voltage


