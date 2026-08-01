"""Topology contraction for the numerical AC power-flow network."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

import numpy as np

from o_grid.acpf.models.case import BranchData, BusData, PowerFlowCase
from o_grid.acpf.models.lcc import LCCData
from o_grid.acpf.models.shunt import ShuntControlData
from o_grid.acpf.models.svc import SVCData
from o_grid.models import ACBusTypes


@dataclass(slots=True)
class ReducedPowerFlowCase:
    """Numerical case and mapping back to every original bus."""

    case: PowerFlowCase
    original_to_reduced: np.ndarray

    def expand_voltage(self, voltage: np.ndarray) -> np.ndarray:
        return voltage[self.original_to_reduced]

    def representative_buses(self, original: PowerFlowCase) -> dict[int, int]:
        """Map each original bus number to its retained representative."""
        return {
            original.buses[index].number: self.case.buses[reduced_index].number
            for index, reduced_index in enumerate(self.original_to_reduced)
        }

    def sync_control_state(self, original: PowerFlowCase) -> None:
        """Copy solved mutable controls back to the original, uncontracted case."""
        reduced_number = self.representative_buses(original)
        reduced_branches = {
            (branch.from_bus, branch.to_bus, branch.circuit): branch
            for branch in self.case.branches
        }
        for branch in original.branches:
            key = (reduced_number[branch.from_bus], reduced_number[branch.to_bus], branch.circuit)
            solved = reduced_branches.get(key) or reduced_branches.get((key[1], key[0], key[2]))
            if solved is not None:
                branch.tap = solved.tap
                branch.phase_shift = solved.phase_shift

        original_buses = {bus.number: bus for bus in original.buses}
        for source, solved in zip(original.shunt_controls or [], self.case.shunt_controls or []):
            delta = solved.reactive_power - source.reactive_power
            original_buses[source.bus].shunt_susceptance += delta / original.base_mva
            source.reactive_power = solved.reactive_power
        for source, solved in zip(original.svcs or [], self.case.svcs or []):
            delta = solved.reactive_power - source.reactive_power
            original_buses[source.bus].reactive_generation += delta
            source.reactive_power = solved.reactive_power
        for source, solved in zip(original.lccs or [], self.case.lccs or []):
            rectifier = original_buses[source.rectifier_bus]
            inverter = original_buses[source.inverter_bus]
            rectifier.active_load += solved.p_rectifier_mw - source.p_rectifier_mw
            rectifier.reactive_load += solved.q_rectifier_mvar - source.q_rectifier_mvar
            inverter.active_generation += solved.p_inverter_mw - source.p_inverter_mw
            inverter.reactive_load += solved.q_inverter_mvar - source.q_inverter_mvar
            for item in fields(source):
                setattr(source, item.name, getattr(solved, item.name))


def reduce_closed_switches(case: PowerFlowCase) -> ReducedPowerFlowCase:
    """Contract switches and electrically equivalent low-impedance jumper buses."""
    _initialize_auxiliary_bus_voltages(case)
    parent = list(range(len(case.buses)))
    indices = case.bus_index

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    external_degree = {bus.number: 0 for bus in case.buses}
    for branch in case.branches:
        external_degree[branch.from_bus] += 1
        external_degree[branch.to_bus] += 1
        if _should_reduce_branch(case, branch):
            union(indices[branch.from_bus], indices[branch.to_bus])

    groups: dict[int, list[int]] = {}
    for index in range(len(case.buses)):
        groups.setdefault(find(index), []).append(index)
    if all(len(group) == 1 for group in groups.values()):
        return ReducedPowerFlowCase(case, np.arange(len(case.buses), dtype=np.int64))

    reduced_buses: list[BusData] = []
    original_to_reduced = np.empty(len(case.buses), dtype=np.int64)
    bus_mapping: dict[int, int] = {}
    kind_priority = {ACBusTypes.PQ: 0, ACBusTypes.PV: 1, ACBusTypes.REF: 2, ACBusTypes.SLACK: 2}
    for reduced_index, members in enumerate(groups.values()):
        representative_index = max(
            members,
            key=lambda index: (
                kind_priority[case.buses[index].kind],
                external_degree[case.buses[index].number],
            ),
        )
        representative = case.buses[representative_index]
        reduced_buses.append(
            BusData(
                number=representative.number,
                name=representative.name,
                kind=representative.kind,
                voltage=representative.voltage,
                angle=representative.angle,
                active_generation=sum(case.buses[index].active_generation for index in members),
                reactive_generation=sum(case.buses[index].reactive_generation for index in members),
                active_load=sum(case.buses[index].active_load for index in members),
                reactive_load=sum(case.buses[index].reactive_load for index in members),
                shunt_susceptance=sum(case.buses[index].shunt_susceptance for index in members),
                minimum_voltage=min(case.buses[index].minimum_voltage for index in members),
                maximum_voltage=max(case.buses[index].maximum_voltage for index in members),
                base_voltage=representative.base_voltage,
                voltage_group=representative.voltage_group,
                minimum_reactive_generation=(
                    sum(case.buses[index].minimum_reactive_generation or 0.0 for index in members)
                    if all(
                        case.buses[index].minimum_reactive_generation is not None
                        for index in members
                        if case.buses[index].kind == ACBusTypes.PV
                    )
                    else None
                ),
                maximum_reactive_generation=(
                    sum(case.buses[index].maximum_reactive_generation or 0.0 for index in members)
                    if all(
                        case.buses[index].maximum_reactive_generation is not None
                        for index in members
                        if case.buses[index].kind == ACBusTypes.PV
                    )
                    else None
                ),
            )
        )
        for index in members:
            original_to_reduced[index] = reduced_index
            bus_mapping[case.buses[index].number] = representative.number

    reduced_branches = []
    for branch in case.branches:
        from_bus = bus_mapping[branch.from_bus]
        to_bus = bus_mapping[branch.to_bus]
        if from_bus == to_bus:
            continue
        reduced_branches.append(
            BranchData(
                from_bus=from_bus,
                to_bus=to_bus,
                circuit=branch.circuit,
                resistance=branch.resistance,
                reactance=branch.reactance,
                charging=branch.charging,
                tap=branch.tap,
                phase_shift=branch.phase_shift,
                rating=branch.rating,
                is_switch=branch.is_switch,
                controlled_bus=(
                    bus_mapping[branch.controlled_bus]
                    if branch.controlled_bus is not None
                    else None
                ),
                minimum_tap=branch.minimum_tap,
                maximum_tap=branch.maximum_tap,
                target_voltage=branch.target_voltage,
            )
        )
    reduced_svcs = [
        SVCData(
            bus=bus_mapping[control.bus],
            controlled_bus=bus_mapping[control.controlled_bus],
            mode=control.mode,
            slope=control.slope,
            reactive_power=control.reactive_power,
            minimum_reactive_power=control.minimum_reactive_power,
            maximum_reactive_power=control.maximum_reactive_power,
            reference_voltage=control.reference_voltage,
        )
        for control in case.svcs or []
    ]
    reduced_shunts = [
        ShuntControlData(
            bus=bus_mapping[control.bus],
            controlled_bus=bus_mapping[control.controlled_bus],
            reactive_power=control.reactive_power,
            minimum_reactive_power=control.minimum_reactive_power,
            maximum_reactive_power=control.maximum_reactive_power,
            minimum_voltage=control.minimum_voltage,
            maximum_voltage=control.maximum_voltage,
            fixed=control.fixed,
        )
        for control in case.shunt_controls or []
    ]
    reduced = PowerFlowCase(
        case.base_mva,
        reduced_buses,
        reduced_branches,
        reduced_svcs,
        reduced_shunts,
        [
            LCCData(
                link_id=control.link_id,
                link_name=control.link_name,
                rectifier_bus=bus_mapping[control.rectifier_bus],
                inverter_bus=bus_mapping[control.inverter_bus],
                pdc_mw=control.pdc_mw,
                p_rectifier_mw=control.p_rectifier_mw,
                p_inverter_mw=control.p_inverter_mw,
                q_rectifier_mvar=control.q_rectifier_mvar,
                q_inverter_mvar=control.q_inverter_mvar,
                rdc_ohm=control.rdc_ohm,
                vdc_rectifier_kv=control.vdc_rectifier_kv,
                vdc_inverter_kv=control.vdc_inverter_kv,
                rectifier_slack=control.rectifier_slack,
                inverter_slack=control.inverter_slack,
                rectifier_control_mode=control.rectifier_control_mode,
                inverter_control_mode=control.inverter_control_mode,
                alpha_deg=control.alpha_deg,
                gamma_deg=control.gamma_deg,
                xcr_percent=control.xcr_percent,
                xci_percent=control.xci_percent,
                rectifier_bridge_voltage_kv=control.rectifier_bridge_voltage_kv,
                inverter_bridge_voltage_kv=control.inverter_bridge_voltage_kv,
                rectifier_nominal_mva=control.rectifier_nominal_mva,
                inverter_nominal_mva=control.inverter_nominal_mva,
                rectifier_poles=control.rectifier_poles,
                inverter_poles=control.inverter_poles,
                tap_rectifier=control.tap_rectifier,
                tap_inverter=control.tap_inverter,
                tap_rectifier_min=control.tap_rectifier_min,
                tap_rectifier_max=control.tap_rectifier_max,
                tap_inverter_min=control.tap_inverter_min,
                tap_inverter_max=control.tap_inverter_max,
                vbase_kv=control.vbase_kv,
                power_base_mw=control.power_base_mw,
                mu_rectifier_deg=control.mu_rectifier_deg,
                mu_inverter_deg=control.mu_inverter_deg,
            )
            for control in case.lccs or []
        ],
    )
    _initialize_auxiliary_bus_voltages(reduced)
    return ReducedPowerFlowCase(reduced, original_to_reduced)


def _initialize_auxiliary_bus_voltages(case: PowerFlowCase) -> None:
    buses = {bus.number: bus for bus in case.buses}
    for branch in case.branches:
        if math.hypot(branch.resistance, branch.reactance) > 1.05e-3 or abs(branch.tap) <= 1e-12:
            continue
        from_bus = buses[branch.from_bus]
        to_bus = buses[branch.to_bus]
        from_auxiliary = from_bus.voltage_group == "U"
        to_auxiliary = to_bus.voltage_group == "U"
        if from_auxiliary == to_auxiliary:
            continue
        if to_auxiliary:
            to_bus.voltage = from_bus.voltage / branch.tap
            to_bus.angle = from_bus.angle - branch.phase_shift
        else:
            from_bus.voltage = to_bus.voltage * branch.tap
            from_bus.angle = to_bus.angle + branch.phase_shift


def _should_reduce_branch(case: PowerFlowCase, branch: BranchData) -> bool:
    impedance = math.hypot(branch.resistance, branch.reactance)
    if branch.is_switch:
        return True
    if abs(branch.tap - 1.0) > 1e-9 or abs(branch.phase_shift) > 1e-9:
        return False
    if impedance <= 2.000001e-4:
        return True
    if impedance > 1.05e-3:
        return False
    buses = {bus.number: bus for bus in case.buses}
    from_bus = buses[branch.from_bus]
    to_bus = buses[branch.to_bus]
    same_voltage = (
        bool(from_bus.voltage_group)
        and from_bus.voltage_group == to_bus.voltage_group
        or from_bus.base_voltage > 0.0
        and to_bus.base_voltage > 0.0
        and abs(from_bus.base_voltage - to_bus.base_voltage) <= 1e-9
    )
    if not same_voltage or branch.rating <= 0.0:
        return False
    impedance_value = complex(branch.resistance, branch.reactance)
    admittance = 1.0 / impedance_value
    tap = branch.tap * np.exp(1j * branch.phase_shift)
    from_voltage = from_bus.voltage * np.exp(1j * from_bus.angle)
    to_voltage = to_bus.voltage * np.exp(1j * to_bus.angle)
    charging = 0.5j * branch.charging
    current = (admittance + charging) / abs(tap) ** 2 * from_voltage
    current -= admittance / np.conj(tap) * to_voltage
    apparent_flow = abs(from_voltage * np.conj(current)) * case.base_mva
    return apparent_flow > branch.rating * 1.25
