"""Python power-flow case models built from parsed infrasys components."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from o_grid.acpf.models.csc import apply_csc_to_branches
from o_grid.acpf.models.lcc import LCCData, build_lcc_data
from o_grid.acpf.models.pst import apply_pst_to_branch
from o_grid.acpf.models.shunt import ShuntControlData
from o_grid.acpf.models.svc import SVCData
from o_grid.models import (
    ACBus,
    ACBusTypes,
    ACLine,
    BusShuntBank,
    CircuitState,
    ControllableSeriesCompensator,
    LineShuntBank,
    LTCTransformer,
    PhaseShiftingTransformer,
    StaticVARCompensator,
    SwitchDevice,
    TransformerDevice,
)
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
    base_voltage: float
    voltage_group: str
    minimum_reactive_generation: float | None = None
    maximum_reactive_generation: float | None = None


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
    is_switch: bool = False
    controlled_bus: int | None = None
    minimum_tap: float = 0.0
    maximum_tap: float = 0.0
    target_voltage: float = 1.0


@dataclass(slots=True)
class PowerFlowCase:
    base_mva: float
    buses: list[BusData]
    branches: list[BranchData]
    svcs: list[SVCData] | None = None
    shunt_controls: list[ShuntControlData] | None = None
    lccs: list[LCCData] | None = None

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
    svcs: list[SVCData] = []
    shunt_controls: list[ShuntControlData] = []
    lccs = build_lcc_data(parsed.components_by_block)
    _apply_supplemental_components(parsed, buses, base_mva, svcs, shunt_controls)
    _apply_lcc_injections(buses, lccs)
    branch_types = (
        ACLine,
        LTCTransformer,
        PhaseShiftingTransformer,
        TransformerDevice,
        SwitchDevice,
    )
    branch_components = (
        component
        for component_type in branch_types
        for component in parsed.system.get_components(component_type)
        if _branch_is_in_service(component)
    )
    branches = [_build_branch(component, base_mva) for component in branch_components]
    apply_csc_to_branches(
        parsed.system.get_components(ControllableSeriesCompensator), branches, BranchData
    )
    if not buses:
        raise ValueError("The infrasys system contains no AC buses")
    if not branches:
        raise ValueError("The infrasys system contains no AC branches")
    if not any(bus.kind in {ACBusTypes.REF, ACBusTypes.SLACK} for bus in buses):
        raise ValueError("The infrasys system contains no reference bus")
    return PowerFlowCase(
        base_mva=base_mva,
        buses=buses,
        branches=branches,
        svcs=svcs,
        shunt_controls=shunt_controls,
        lccs=lccs,
    )


def _apply_supplemental_components(
    parsed: ParsedAnaredeSystem,
    buses: list[BusData],
    base_mva: float,
    svcs: list[SVCData],
    shunt_controls: list[ShuntControlData],
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

    bank_totals: dict[int, list[tuple[float, int, int]]] = defaultdict(list)
    for bank_type in (BusShuntBank, LineShuntBank):
        for bank in parsed.system.get_components(bank_type):
            parent = int(getattr(bank, "parent_record_index", 0) or 0)
            reactive_power = _magnitude(getattr(bank, "reactive_power_per_unit", None))
            total_units = _integer(getattr(bank, "total_units", 0))
            units_in_operation = _integer(getattr(bank, "units_in_operation", 0))
            bank_totals[parent].append((reactive_power, total_units, units_in_operation))

    for record_index, component in enumerate(parsed.components_by_block.get("DBSH", []), start=1):
        values = _pwf_values(component)
        bus = by_number.get(_integer(values.get("from_bus")))
        if bus is not None:
            if str(values.get("clear_dbar_data") or "N").upper() == "S":
                bus.shunt_susceptance = 0.0
            stages = bank_totals.get(record_index, [])
            initial = (
                sum(power * operating for power, _, operating in stages)
                if stages
                else float(values.get("initial_reactive_injection") or 0.0)
            )
            minimum = sum(min(0.0, power * total) for power, total, _ in stages)
            maximum = sum(max(0.0, power * total) for power, total, _ in stages)
            if not stages:
                minimum, maximum = min(0.0, initial), max(0.0, initial)
            bus.shunt_susceptance += initial / base_mva
            controlled_number = _integer(values.get("controlled_bus"), bus.number)
            controlled_bus = by_number.get(controlled_number, bus)
            shunt_controls.append(
                ShuntControlData(
                    bus=bus.number,
                    controlled_bus=controlled_bus.number,
                    reactive_power=initial,
                    minimum_reactive_power=minimum,
                    maximum_reactive_power=maximum,
                    minimum_voltage=float(
                        values.get("minimum_voltage") or controlled_bus.minimum_voltage
                    ),
                    maximum_voltage=float(
                        values.get("maximum_voltage") or controlled_bus.maximum_voltage
                    ),
                    fixed=str(values.get("control_mode") or "F").upper() == "F",
                )
            )

    for component in parsed.components_by_block.get("DSHL", []):
        values = _pwf_values(component)
        from_bus = by_number.get(_integer(values.get("from_bus")))
        to_bus = by_number.get(_integer(values.get("to_bus")))
        if from_bus is not None and values.get("state_from", "L") != "D":
            from_bus.shunt_susceptance += float(values.get("shunt_from") or 0.0) / base_mva
        if to_bus is not None and values.get("state_to", "L") != "D":
            to_bus.shunt_susceptance += float(values.get("shunt_to") or 0.0) / base_mva

    for component in parsed.system.get_components(StaticVARCompensator):
        values = _pwf_values(component)
        bus = by_number.get(_bus_number(getattr(component, "bus", values.get("bus"))))
        if bus is not None and getattr(component, "available", True):
            reactive_power = _magnitude(
                getattr(component, "reactive_generation", None),
                values.get("reactive_generation", 0.0),
            )
            bus.reactive_generation += reactive_power
            controlled_number = _bus_number(
                getattr(component, "controlled_bus", None) or bus.number
            )
            controlled_bus = by_number.get(controlled_number, bus)
            svcs.append(
                SVCData(
                    bus=bus.number,
                    controlled_bus=controlled_bus.number,
                    mode=str(getattr(component, "control_mode", "I") or "I"),
                    slope=_magnitude(getattr(component, "slope", None)) * 0.01,
                    reactive_power=reactive_power,
                    minimum_reactive_power=_magnitude(
                        getattr(component, "min_reactive_generation", None)
                    ),
                    maximum_reactive_power=_magnitude(
                        getattr(component, "max_reactive_generation", None)
                    ),
                    reference_voltage=controlled_bus.voltage,
                )
            )


def _apply_lcc_injections(buses: list[BusData], lccs: list[LCCData]) -> None:
    by_number = {bus.number: bus for bus in buses}
    for lcc in lccs:
        rectifier = by_number.get(lcc.rectifier_bus)
        inverter = by_number.get(lcc.inverter_bus)
        if rectifier is not None:
            rectifier.active_load += lcc.p_rectifier_mw
            rectifier.reactive_load += lcc.q_rectifier_mvar
        if inverter is not None:
            inverter.active_generation += lcc.p_inverter_mw
            inverter.reactive_load += lcc.q_inverter_mvar


def _build_bus(component: object, base_mva: float) -> BusData:
    if not isinstance(component, ACBus) or component.number is None:
        raise TypeError("DBAR components must be numbered ACBus instances")
    limits = component.voltage_limits
    voltage_group = getattr(component, "voltage_base_group", None)
    return BusData(
        number=_integer(component.number),
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
        base_voltage=_magnitude(getattr(component, "base_voltage", None)),
        voltage_group=str(getattr(voltage_group, "group", voltage_group) or ""),
        minimum_reactive_generation=(
            _magnitude(component.min_reactive_generation)
            if component.min_reactive_generation is not None
            else None
        ),
        maximum_reactive_generation=(
            _magnitude(component.max_reactive_generation)
            if component.max_reactive_generation is not None
            else None
        ),
    )


def _build_branch(component: object, base_mva: float) -> BranchData:
    values = _pwf_values(component)
    from_bus = getattr(component, "from_bus", values.get("from_bus"))
    to_bus = getattr(component, "to_bus", values.get("to_bus"))
    controlled = getattr(component, "controlled_bus", None)
    controlled_number = _bus_number(controlled) if controlled is not None else None
    controlled_voltage = _magnitude(getattr(controlled, "initial_voltage", None), 1.0)
    branch = BranchData(
        from_bus=_bus_number(from_bus),
        to_bus=_bus_number(to_bus),
        circuit=_integer(getattr(component, "line_circuit", None), 1),
        resistance=_magnitude(getattr(component, "r", None), values.get("resistance", 0.0)) * 0.01,
        reactance=_magnitude(getattr(component, "x", None), values.get("reactance", 0.0)) * 0.01,
        charging=float(values.get("susceptance") or 0.0) / base_mva,
        tap=float(values.get("tap") or 1.0),
        phase_shift=-math.radians(float(values.get("phase_shift") or 0.0)),
        rating=_magnitude(
            getattr(component, "normal_capacity", None), values.get("normal_capacity", 0.0)
        ),
        is_switch=isinstance(component, SwitchDevice),
        controlled_bus=controlled_number,
        minimum_tap=float(values.get("tap_minimum") or 0.0),
        maximum_tap=float(values.get("tap_maximum") or 0.0),
        target_voltage=controlled_voltage,
    )
    if isinstance(component, PhaseShiftingTransformer):
        apply_pst_to_branch(component, branch)
    return branch


def _branch_is_in_service(component: object) -> bool:
    return (
        bool(getattr(component, "available", True))
        and getattr(component, "from_bus_opening", CircuitState.CLOSED) != CircuitState.OPEN
        and getattr(component, "to_bus_opening", CircuitState.CLOSED) != CircuitState.OPEN
    )


def _base_mva(parsed: ParsedAnaredeSystem) -> float:
    for constant in parsed.components_by_block.get("DCTE", []):
        if str(getattr(constant, "mnemonic", "")).strip().upper() == "BASE":
            return _magnitude(getattr(constant, "value", None), 100.0)
    return 100.0


def _bus_number(value: object) -> int:
    number = getattr(value, "number", value)
    return int(float(str(number)))


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value))) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _magnitude(value: object, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    magnitude = get_magnitude(value)
    return float(magnitude)


def _pwf_values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}
