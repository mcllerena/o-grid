"""Python power-flow case models built from parsed infrasys components."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from o_grid.acpf.models.lcc import build_lcc_injections
from o_grid.models import ACBus, ACBusTypes
from o_grid.parser import ParsedAnaredeSystem
from o_grid.units import get_magnitude


@dataclass(slots=True)
class BusData:
    number: int
    name: str
    kind: ACBusTypes
    voltage: float
    angle: float
    active_generation: float
    reactive_generation: float
    active_load: float
    reactive_load: float
    shunt_susceptance: float
    minimum_voltage: float
    maximum_voltage: float


@dataclass(slots=True)
class BranchData:
    from_bus: int
    to_bus: int
    circuit: int
    resistance: float
    reactance: float
    charging: float
    tap: float
    phase_shift: float
    rating: float


@dataclass(slots=True)
class PowerFlowCase:
    base_mva: float
    buses: list[BusData]
    branches: list[BranchData]

    @property
    def bus_index(self) -> dict[int, int]:
        return {bus.number: index for index, bus in enumerate(self.buses)}

    @property
    def slack_indices(self) -> np.ndarray:
        return np.array(
            [
                index
                for index, bus in enumerate(self.buses)
                if bus.kind in {ACBusTypes.REF, ACBusTypes.SLACK}
            ],
            dtype=np.int64,
        )

    @property
    def pv_indices(self) -> np.ndarray:
        return np.array(
            [index for index, bus in enumerate(self.buses) if bus.kind == ACBusTypes.PV],
            dtype=np.int64,
        )

    @property
    def pq_indices(self) -> np.ndarray:
        return np.array(
            [index for index, bus in enumerate(self.buses) if bus.kind == ACBusTypes.PQ],
            dtype=np.int64,
        )

    @property
    def specified_power(self) -> np.ndarray:
        return np.array(
            [
                complex(
                    bus.active_generation - bus.active_load,
                    bus.reactive_generation - bus.reactive_load,
                )
                / self.base_mva
                for bus in self.buses
            ],
            dtype=np.complex128,
        )

    @property
    def initial_voltage(self) -> np.ndarray:
        return np.array(
            [bus.voltage * np.exp(1j * bus.angle) for bus in self.buses],
            dtype=np.complex128,
        )


def build_power_flow_case(parsed: ParsedAnaredeSystem) -> PowerFlowCase:
    """Build numerical case data from the components in an infrasys-backed parse result."""
    base_mva = _base_mva(parsed)
    buses = [_build_bus(component, base_mva) for component in parsed.components_by_block["DBAR"]]
    _apply_supplemental_components(parsed, buses, base_mva)
    branches = [_build_branch(component) for component in parsed.components_by_block["DLIN"]]
    branches.extend(
        _build_csc_branch(component) for component in parsed.components_by_block.get("DCSC", [])
    )
    if not buses:
        raise ValueError("The infrasys system contains no AC buses")
    if not branches:
        raise ValueError("The infrasys system contains no AC branches")
    if not any(bus.kind in {ACBusTypes.REF, ACBusTypes.SLACK} for bus in buses):
        raise ValueError("The infrasys system contains no reference bus")
    return PowerFlowCase(base_mva=base_mva, buses=buses, branches=branches)


def _apply_supplemental_components(
    parsed: ParsedAnaredeSystem, buses: list[BusData], base_mva: float
) -> None:
    by_number = {bus.number: bus for bus in buses}
    for component in parsed.components_by_block.get("DCAI", []):
        values = _pwf_values(component)
        bus = by_number.get(_bus_number(getattr(component, "bus", values.get("bus"))))
        if bus is not None:
            bus.active_load += _magnitude(
                getattr(component, "active_power", None), values.get("active_power", 0.0)
            )
            bus.reactive_load += _magnitude(
                getattr(component, "reactive_power", None), values.get("reactive_power", 0.0)
            )

    for component in parsed.components_by_block.get("DBSH", []):
        values = _pwf_values(component)
        bus = by_number.get(int(float(values.get("from_bus") or 0)))
        if bus is not None:
            bus.shunt_susceptance += (
                float(values.get("initial_reactive_injection") or 0.0) / base_mva
            )

    for component in parsed.components_by_block.get("DSHL", []):
        values = _pwf_values(component)
        from_bus = by_number.get(int(float(values.get("from_bus") or 0)))
        to_bus = by_number.get(int(float(values.get("to_bus") or 0)))
        if from_bus is not None and values.get("state_from", "L") != "D":
            from_bus.shunt_susceptance += float(values.get("shunt_from") or 0.0) / base_mva
        if to_bus is not None and values.get("state_to", "L") != "D":
            to_bus.shunt_susceptance += float(values.get("shunt_to") or 0.0) / base_mva

    for component in parsed.components_by_block.get("DCER", []):
        values = _pwf_values(component)
        bus = by_number.get(_bus_number(getattr(component, "bus", values.get("bus"))))
        if bus is not None:
            bus.reactive_generation += _magnitude(
                getattr(component, "reactive_generation", None),
                values.get("reactive_generation", 0.0),
            )

    for injection in build_lcc_injections(parsed.components_by_block):
        bus = by_number.get(injection.bus)
        if bus is not None:
            if injection.active_mw >= 0.0:
                bus.active_generation += injection.active_mw
            else:
                bus.active_load -= injection.active_mw
            bus.reactive_load -= injection.reactive_mvar


def _build_bus(component: object, base_mva: float) -> BusData:
    if not isinstance(component, ACBus) or component.number is None:
        raise TypeError("DBAR components must be numbered ACBus instances")
    limits = component.voltage_limits
    return BusData(
        number=int(float(component.number)),
        name=component.name,
        kind=component.bustype or ACBusTypes.PQ,
        voltage=_magnitude(component.initial_voltage, 1.0),
        angle=math.radians(_magnitude(component.angle)),
        active_generation=_magnitude(component.active_generation),
        reactive_generation=_magnitude(component.reactive_generation),
        active_load=_magnitude(component.active_load),
        reactive_load=_magnitude(component.reactive_load),
        shunt_susceptance=_magnitude(component.capacitor_reactor) / base_mva,
        minimum_voltage=float(limits.min) if limits is not None else 0.9,
        maximum_voltage=float(limits.max) if limits is not None else 1.1,
    )


def _build_branch(component: object) -> BranchData:
    values = _pwf_values(component)
    from_bus = getattr(component, "from_bus", values.get("from_bus"))
    to_bus = getattr(component, "to_bus", values.get("to_bus"))
    return BranchData(
        from_bus=_bus_number(from_bus),
        to_bus=_bus_number(to_bus),
        circuit=int(float(getattr(component, "line_circuit", None) or 1)),
        resistance=_magnitude(getattr(component, "r", None), values.get("resistance", 0.0)) * 0.01,
        reactance=_magnitude(getattr(component, "x", None), values.get("reactance", 0.0)) * 0.01,
        charging=float(values.get("susceptance") or 0.0) * 0.01,
        tap=float(values.get("tap") or 1.0),
        phase_shift=-math.radians(float(values.get("phase_shift") or 0.0)),
        rating=_magnitude(
            getattr(component, "normal_capacity", None), values.get("normal_capacity", 0.0)
        ),
    )


def _build_csc_branch(component: object) -> BranchData:
    values = _pwf_values(component)
    return BranchData(
        from_bus=_bus_number(getattr(component, "from_bus", values.get("from_bus"))),
        to_bus=_bus_number(getattr(component, "to_bus", values.get("to_bus"))),
        circuit=int(float(getattr(component, "dcsc_circuit", None) or 1)),
        resistance=0.0,
        reactance=_magnitude(
            getattr(component, "initial_reactance", None),
            values.get("initial_reactance", 0.0),
        )
        * 0.01,
        charging=0.0,
        tap=1.0,
        phase_shift=0.0,
        rating=_magnitude(
            getattr(component, "dcsc_capacity", None), values.get("dcsc_capacity", 0.0)
        ),
    )


def _base_mva(parsed: ParsedAnaredeSystem) -> float:
    for constant in parsed.components_by_block.get("DCTE", []):
        if str(getattr(constant, "mnemonic", "")).strip().upper() == "BASE":
            return _magnitude(getattr(constant, "value", None), 100.0)
    return 100.0


def _bus_number(value: object) -> int:
    number = getattr(value, "number", value)
    return int(float(str(number)))


def _magnitude(value: object, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    magnitude = get_magnitude(value)
    return float(magnitude)


def _pwf_values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}
