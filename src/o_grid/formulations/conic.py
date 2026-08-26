"""W-space SOC and SDP exporters for Clarabel."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from o_grid.acpf.models.case import PowerFlowCase
from o_grid.solvers import ClarabelBridge, ClarabelResult

MAX_DENSE_SDP_BUSES = 50


@dataclass
class ConicModel:
    case: PowerFlowCase
    formulation: str
    problem: dict[str, Any]
    variable_names: list[tuple[str, int, int | None]]
    solution: ClarabelResult | None = None
    vm: dict[int, float] | None = None
    va: dict[int, float] | None = None

    @property
    def _case(self) -> PowerFlowCase:
        """Compatibility alias used by shared ACOPF metric helpers."""
        return self.case


def _admittance(case: PowerFlowCase) -> list[dict[str, float]]:
    values = []
    for branch in case.branches:
        z2 = branch.resistance**2 + branch.reactance**2
        g = branch.resistance / z2 if z2 > 1e-12 else 0.0
        b = -branch.reactance / z2 if z2 > 1e-12 else 0.0
        tap = branch.tap if abs(branch.tap) > 1e-12 else 1.0
        cosine = math.cos(branch.phase_shift)
        sine = math.sin(branch.phase_shift)
        self_b = b + branch.charging / 2.0
        values.append(
            {
                "yff_g": g / tap**2,
                "yff_b": self_b / tap**2,
                "yft_g": (-g * cosine + b * sine) / tap,
                "yft_b": (-g * sine - b * cosine) / tap,
                "ytf_g": (-g * cosine - b * sine) / tap,
                "ytf_b": (g * sine - b * cosine) / tap,
                "ytt_g": g,
                "ytt_b": self_b,
            }
        )
    return values


class _Builder:
    def __init__(self, case: PowerFlowCase, formulation: str) -> None:
        self.case = case
        self.formulation = formulation
        self.names: list[tuple[str, int, int | None]] = []
        self.index: dict[tuple[str, int, int | None], int] = {}
        self.rows: list[dict[int, float]] = []
        self.bounds: list[float] = []
        self.cones: list[dict[str, Any]] = []
        self.q: list[float] = []
        self.admittance = _admittance(case)
        self.bus_index = case.bus_index

    def variable(self, kind: str, first: int, second: int | None = None) -> int:
        key = (kind, first, second)
        if key not in self.index:
            self.index[key] = len(self.names)
            self.names.append(key)
            self.q.append(0.0)
        return self.index[key]

    def row(self, coefficients: dict[int, float], rhs: float, cone: str = "zero") -> None:
        self.rows.append(coefficients)
        self.bounds.append(rhs)
        self.cones.append({"type": cone, "dimension": 1})

    def cone_rows(
        self,
        rows: list[dict[int, float]],
        cone: str,
        dimension: int,
        bounds: list[float] | None = None,
    ) -> None:
        self.rows.extend(rows)
        self.bounds.extend(bounds if bounds is not None else [0.0] * len(rows))
        self.cones.append({"type": cone, "dimension": dimension})

    def pair(self, i: int, j: int) -> tuple[int, int]:
        first, second = sorted((i, j))
        return self.variable("wr", first, second), self.variable("wi", first, second)

    def pair_coeff(
        self, coefficients: dict[int, float], i: int, j: int, real: float, imag: float
    ) -> None:
        wr, wi = self.pair(i, j)
        coefficients[wr] = coefficients.get(wr, 0.0) + real
        coefficients[wi] = coefficients.get(wi, 0.0) + (imag if i < j else -imag)

    def injection(self, bus: int, reactive: bool) -> dict[int, float]:
        coefficients: dict[int, float] = {}
        diagonal = self.variable("w", bus)
        if reactive:
            coefficients[diagonal] = -self.case.buses[self.bus_index[bus]].shunt_susceptance
        for index, branch in enumerate(self.case.branches):
            if branch.from_bus == bus:
                other = branch.to_bus
                values = self.admittance[index]
                self_g, self_b = values["yff_g"], values["yff_b"]
                mutual_g, mutual_b = values["yft_g"], values["yft_b"]
            elif branch.to_bus == bus:
                other = branch.from_bus
                values = self.admittance[index]
                self_g, self_b = values["ytt_g"], values["ytt_b"]
                mutual_g, mutual_b = values["ytf_g"], values["ytf_b"]
            else:
                continue
            coefficients[diagonal] = coefficients.get(diagonal, 0.0) + (
                -self_b if reactive else self_g
            )
            self.pair_coeff(
                coefficients,
                bus,
                other,
                -mutual_b if reactive else mutual_g,
                mutual_g if reactive else mutual_b,
            )
        return coefficients

    def branch_flow(self, index: int, at_from: bool, reactive: bool) -> dict[int, float]:
        branch = self.case.branches[index]
        values = self.admittance[index]
        bus = branch.from_bus if at_from else branch.to_bus
        other = branch.to_bus if at_from else branch.from_bus
        self_key = "yff_" if at_from else "ytt_"
        mutual_key = "yft_" if at_from else "ytf_"
        self_value = values[self_key + ("b" if reactive else "g")]
        mutual_real = values[mutual_key + ("b" if reactive else "g")]
        mutual_imag = values[mutual_key + ("g" if reactive else "b")]
        coefficients = {
            self.variable("w", bus): -self_value if reactive else self_value
        }
        self.pair_coeff(
            coefficients, bus, other, -mutual_real if reactive else mutual_real, mutual_imag
        )
        return coefficients

    def bound(self, variable: int, lower: float, upper: float) -> None:
        self.row({variable: -1.0}, -lower, "nonnegative")
        self.row({variable: 1.0}, upper, "nonnegative")

    def matrix_entry(
        self, coefficients: dict[int, float], i: int, j: int, value: float, imaginary: bool = False
    ) -> None:
        if i == j:
            if not imaginary:
                variable = self.variable("w", i)
                coefficients[variable] = coefficients.get(variable, 0.0) + value
            return
        first, second = sorted((i, j))
        variable = self.variable("wi" if imaginary else "wr", first, second)
        coefficients[variable] = coefficients.get(variable, 0.0) + value

    def edge_psd_rows(self, i: int, j: int) -> list[dict[int, float]]:
        """Return the SOC representation of the 2x2 Hermitian PSD edge block."""
        w_i = self.variable("w", i)
        w_j = self.variable("w", j)
        wr, wi = self.pair(i, j)
        orientation = 1.0 if i < j else -1.0
        return [
            {w_i: -0.5, w_j: -0.5},
            {w_i: -0.5, w_j: 0.5},
            {wr: -1.0},
            {wi: -orientation},
        ]

    def build(self) -> ConicModel:
        buses = [bus.number for bus in self.case.buses]
        is_soc = self.formulation in {
            "SOCWRPowerModel",
            "SOCWRConicPowerModel",
            "SOCBFPowerModel",
            "SOCBFConicPowerModel",
        }
        is_dense_sdp = self.formulation == "SDPWRMPowerModel"
        is_sparse_sdp = self.formulation == "SparseSDPWRMPowerModel"
        is_sdp = is_dense_sdp or is_sparse_sdp
        if not is_soc and not is_sdp:
            raise ValueError(f"unsupported conic formulation: {self.formulation}")
        if is_dense_sdp and len(buses) > MAX_DENSE_SDP_BUSES:
            raise ValueError(f"dense SDP formulation supports at most {MAX_DENSE_SDP_BUSES} buses")
        for bus in buses:
            self.variable("w", bus)
        cone_blocks: list[tuple[list[dict[int, float]], str, int, list[float] | None]] = []
        if is_soc:
            for index, branch in enumerate(self.case.branches):
                i, j = self.bus_index[branch.from_bus], self.bus_index[branch.to_bus]
                wr, wi = self.pair(i, j)
                w_i, w_j = self.variable("w", branch.from_bus), self.variable("w", branch.to_bus)
                cone_blocks.append(
                    (
                        [
                            {w_i: -0.5, w_j: -0.5},
                            {w_i: -0.5, w_j: 0.5},
                            {wr: -1.0},
                            {wi: -(1.0 if i < j else -1.0)},
                        ],
                        "second_order",
                        4,
                        None,
                    )
                )
                if branch.rating > 0.0:
                    for at_from in (True, False):
                        p_flow = self.branch_flow(index, at_from, False)
                        q_flow = self.branch_flow(index, at_from, True)
                        cone_blocks.append(
                            (
                                [
                                    {},
                                    {key: -value for key, value in p_flow.items()},
                                    {key: -value for key, value in q_flow.items()},
                                ],
                                "second_order",
                                3,
                                [branch.rating / self.case.base_mva, 0.0, 0.0],
                            )
                        )
        elif is_dense_sdp:
            dimension = 2 * len(buses)
            for i in range(len(buses)):
                for j in range(i + 1, len(buses)):
                    self.variable("wr", i, j)
                    self.variable("wi", i, j)
            rows: list[dict[int, float]] = []
            for row in range(dimension):
                for column in range(row + 1):
                    coefficients: dict[int, float] = {}
                    if row < len(buses) and column < len(buses):
                        self.matrix_entry(coefficients, row, column, 1.0)
                    elif row >= len(buses) and column >= len(buses):
                        self.matrix_entry(coefficients, row - len(buses), column - len(buses), 1.0)
                    elif row >= len(buses) and column != row - len(buses):
                        imaginary_row = row - len(buses)
                        self.matrix_entry(
                            coefficients,
                            column,
                            imaginary_row,
                            -1.0 if column > imaginary_row else 1.0,
                            True,
                        )
                    rows.append({key: -value for key, value in coefficients.items()})
            cone_blocks.append((rows, "positive_semidefinite", dimension, None))
        else:
            for branch in self.case.branches:
                i = self.bus_index[branch.from_bus]
                j = self.bus_index[branch.to_bus]
                cone_blocks.append((self.edge_psd_rows(i, j), "second_order", 4, None))
        svc_by_bus: dict[int, list[tuple[int, Any]]] = {}
        for index, svc in enumerate(self.case.svcs or []):
            svc_by_bus.setdefault(svc.bus, []).append((index, svc))
        shunt_by_bus: dict[int, list[tuple[int, Any]]] = {}
        for index, shunt in enumerate(self.case.shunt_controls or []):
            shunt_by_bus.setdefault(shunt.bus, []).append((index, shunt))
        for bus in self.case.buses:
            w = self.variable("w", bus.number)
            has_generation = (
                abs(bus.active_generation) > 1e-12
                or abs(bus.reactive_generation) > 1e-12
                or bus.kind.name in {"REF", "SLACK"}
            )
            active_upper = (
                max(
                    2 * abs(bus.active_generation),
                    abs(bus.active_load) + self.case.base_mva,
                    self.case.base_mva,
                )
                / self.case.base_mva
            )
            reactive_lower = (
                bus.minimum_reactive_generation
                if bus.minimum_reactive_generation is not None
                else -max(abs(bus.reactive_generation), self.case.base_mva)
            ) / self.case.base_mva
            reactive_upper = (
                bus.maximum_reactive_generation
                if bus.maximum_reactive_generation is not None
                else max(abs(bus.reactive_generation), self.case.base_mva)
            ) / self.case.base_mva
            pg, qg = self.variable("pg", bus.number), self.variable("qg", bus.number)
            self.bound(pg, 0.0, active_upper if has_generation else 0.0)
            self.bound(
                qg,
                reactive_lower if has_generation else 0.0,
                reactive_upper if has_generation else 0.0,
            )
            self.row(
                {**self.injection(bus.number, False), pg: -1.0},
                -bus.active_load / self.case.base_mva,
            )
            q_coefficients = {**self.injection(bus.number, True), qg: -1.0}
            for index, svc in svc_by_bus.get(bus.number, []):
                qsvc = self.variable("qsvc", index)
                self.bound(
                    qsvc,
                    svc.minimum_reactive_power / self.case.base_mva,
                    svc.maximum_reactive_power / self.case.base_mva,
                )
                q_coefficients[qsvc] = -1.0
            for index, shunt in shunt_by_bus.get(bus.number, []):
                qshunt = self.variable("qshunt", index)
                initial = shunt.reactive_power / self.case.base_mva
                self.bound(
                    qshunt,
                    shunt.minimum_reactive_power / self.case.base_mva - initial,
                    shunt.maximum_reactive_power / self.case.base_mva - initial,
                )
                q_coefficients[qshunt] = -1.0
            self.row(q_coefficients, -bus.reactive_load / self.case.base_mva)
            self.row({w: 1.0}, bus.maximum_voltage**2, "nonnegative")
            self.row({w: -1.0}, -(bus.minimum_voltage**2), "nonnegative")
            self.q[w] -= 2 * bus.voltage**2
        for rows, cone, dimension, bounds in cone_blocks:
            self.cone_rows(rows, cone, dimension, bounds)
        problem = {
            "n": len(self.names),
            "m": len(self.rows),
            "P": [],
            "q": self.q,
            "A": [
                [row + 1, column + 1, value]
                for row, coefficients in enumerate(self.rows)
                for column, value in coefficients.items()
                if abs(value) > 1e-14
            ],
            "b": self.bounds,
            "cones": self.cones,
        }
        return ConicModel(self.case, self.formulation, problem, self.names)


def build_conic_model(case: PowerFlowCase, formulation: str) -> ConicModel:
    return _Builder(case, formulation).build()


def solve_conic_model(model: ConicModel, bridge: ClarabelBridge) -> ClarabelResult:
    result = bridge.solve(model.problem)
    model.solution = result
    values = dict(zip(model.variable_names, result.x, strict=False))
    model.vm = {
        bus.number: math.sqrt(max(0.0, values.get(("w", bus.number, None), bus.voltage**2)))
        for bus in model.case.buses
    }
    model.va = {bus.number: bus.angle for bus in model.case.buses}
    for branch in model.case.branches:
        i, j = model.case.bus_index[branch.from_bus], model.case.bus_index[branch.to_bus]
        real = values.get(("wr", min(i, j), max(i, j)), 0.0)
        imag = values.get(("wi", min(i, j), max(i, j)), 0.0) * (1.0 if i < j else -1.0)
        model.va[branch.from_bus] = model.va[branch.to_bus] + math.atan2(imag, real)
    return result
