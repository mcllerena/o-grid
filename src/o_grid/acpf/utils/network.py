"""Network matrix, power injection, and branch-flow calculations."""

from __future__ import annotations

import numpy as np
from scipy.sparse import csc_matrix, lil_matrix
from scipy.sparse.csgraph import connected_components

from o_grid.acpf.models import BranchData, PowerFlowCase
from o_grid.acpf.results import BranchPowerFlowResult, BusPowerFlowResult
from o_grid.models import ACBusTypes

IMPEDANCE_EPSILON = 1e-12


def build_ybus(case: PowerFlowCase) -> csc_matrix:
    """Build a sparse nodal admittance matrix including taps, phase shifts, and shunts."""
    size = len(case.buses)
    matrix = lil_matrix((size, size), dtype=np.complex128)
    indices = case.bus_index
    for branch in case.branches:
        from_index = indices[branch.from_bus]
        to_index = indices[branch.to_bus]
        impedance = complex(branch.resistance, branch.reactance)
        if abs(impedance) < IMPEDANCE_EPSILON:
            raise ValueError(
                f"Branch {branch.from_bus}-{branch.to_bus}-{branch.circuit} has zero impedance"
            )
        admittance = 1.0 / impedance
        charging = 0.5j * branch.charging
        tap = branch.tap * np.exp(1j * branch.phase_shift)
        matrix[from_index, from_index] += (admittance + charging) / abs(tap) ** 2
        matrix[to_index, to_index] += admittance + charging
        matrix[from_index, to_index] -= admittance / np.conj(tap)
        matrix[to_index, from_index] -= admittance / tap
    for index, bus in enumerate(case.buses):
        matrix[index, index] += 1j * bus.shunt_susceptance
    return matrix.tocsc()


def assign_island_reference_buses(case: PowerFlowCase, ybus: csc_matrix) -> list[int]:
    """Assign one numerical slack bus to each island without a reference bus."""
    graph = ybus.copy()
    graph.data = np.ones(graph.nnz, dtype=np.int8)
    island_count, labels = connected_components(graph, directed=False)
    assigned: list[int] = []
    for island in range(island_count):
        indices = np.flatnonzero(labels == island)
        if any(case.buses[index].kind in {ACBusTypes.REF, ACBusTypes.SLACK} for index in indices):
            continue
        candidates = [index for index in indices if case.buses[index].kind == ACBusTypes.PV]
        if not candidates:
            candidates = indices.tolist()
        reference = max(candidates, key=lambda index: case.buses[index].active_generation)
        case.buses[reference].kind = ACBusTypes.SLACK
        assigned.append(case.buses[reference].number)
    return assigned


def calculate_power(ybus: csc_matrix, voltage: np.ndarray) -> np.ndarray:
    """Return per-unit complex bus injections for a complex voltage vector."""
    return voltage * np.conj(ybus @ voltage)


def calculate_bus_results(
    case: PowerFlowCase, ybus: csc_matrix, voltage: np.ndarray
) -> list[BusPowerFlowResult]:
    power = calculate_power(ybus, voltage)
    return [
        BusPowerFlowResult(
            id=bus.number,
            name=bus.name,
            voltage_pu=float(abs(voltage[index])),
            angle_rad=float(np.angle(voltage[index])),
            active_injection_pu=float(power[index].real),
            reactive_injection_pu=float(power[index].imag),
        )
        for index, bus in enumerate(case.buses)
    ]


def calculate_branch_results(
    case: PowerFlowCase, voltage: np.ndarray
) -> list[BranchPowerFlowResult]:
    indices = case.bus_index
    return [
        _branch_result(
            branch,
            voltage[indices[branch.from_bus]],
            voltage[indices[branch.to_bus]],
            case.base_mva,
        )
        for branch in case.branches
    ]


def _branch_result(
    branch: BranchData, from_voltage: complex, to_voltage: complex, base_mva: float
) -> BranchPowerFlowResult:
    impedance = complex(branch.resistance, branch.reactance)
    admittance = 1.0 / impedance
    charging = 0.5j * branch.charging
    tap = branch.tap * np.exp(1j * branch.phase_shift)
    from_current = (admittance + charging) / abs(tap) ** 2 * from_voltage
    from_current -= admittance / np.conj(tap) * to_voltage
    to_current = -admittance / tap * from_voltage + (admittance + charging) * to_voltage
    from_power = from_voltage * np.conj(from_current) * base_mva
    to_power = to_voltage * np.conj(to_current) * base_mva
    maximum_flow = max(abs(from_power), abs(to_power))
    loading = 100.0 * maximum_flow / branch.rating if branch.rating > 0.0 else 0.0
    losses = from_power + to_power
    return BranchPowerFlowResult(
        from_bus=branch.from_bus,
        to_bus=branch.to_bus,
        circuit=branch.circuit,
        active_from_mw=float(from_power.real),
        reactive_from_mvar=float(from_power.imag),
        active_to_mw=float(to_power.real),
        reactive_to_mvar=float(to_power.imag),
        loading_percent=float(loading),
        active_loss_mw=float(losses.real),
        reactive_loss_mvar=float(losses.imag),
    )
