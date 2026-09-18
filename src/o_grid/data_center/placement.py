"""Scenario generation and ranking for large-load placement."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations

import numpy as np

from o_grid.acopf.acopf import solve_acopf
from o_grid.acpf.models import PowerFlowCase
from o_grid.acpf.utils import build_ybus
from o_grid.data_center.models import (
    LoadPlacement,
    PlacementEvaluation,
    PlacementEvaluator,
    PlacementStudy,
)


def placement_scenarios(study: PlacementStudy) -> tuple[LoadPlacement, ...]:
    """Generate binary placement scenarios up to the configured site count."""
    return tuple(
        LoadPlacement(selected_buses=selected, load=study.load)
        for site_count in range(1, study.max_sites + 1)
        for selected in combinations(study.candidate_buses, site_count)
    )


def apply_load(case: PowerFlowCase, placement: LoadPlacement) -> PowerFlowCase:
    """Return a copy of ``case`` with the load divided across selected buses."""
    scenario = deepcopy(case)
    active_per_bus = placement.load.active_mw / len(placement.selected_buses)
    reactive_per_bus = placement.load.reactive_mvar / len(placement.selected_buses)
    buses = {bus.number: bus for bus in scenario.buses}
    for bus_number in placement.selected_buses:
        if bus_number not in buses:
            raise ValueError(f"placement bus {bus_number} is not present in the case")
        buses[bus_number].active_load += active_per_bus
        buses[bus_number].reactive_load += reactive_per_bus
    return scenario


def evaluate_placements(
    case: PowerFlowCase,
    study: PlacementStudy,
    evaluator: PlacementEvaluator,
) -> list[PlacementEvaluation]:
    """Evaluate and rank placement scenarios using a supplied power-flow method."""
    evaluations = [
        evaluator(apply_load(case, placement), placement)
        for placement in placement_scenarios(study)
    ]
    return sorted(evaluations, key=lambda evaluation: (not evaluation.feasible, evaluation.score))


def evaluate_with_acopf(
    case: PowerFlowCase,
    placement: LoadPlacement,
    *,
    tolerance: float = 1.0e-6,
    max_iterations: int = 100,
) -> PlacementEvaluation:
    """Evaluate one placement with the in-process ACOPF feasibility solver."""
    ybus = build_ybus(case)
    solution = solve_acopf(
        case,
        ybus,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
    magnitudes = np.abs(solution.voltage)
    voltage_deviation = float(np.sum((magnitudes - 1.0) ** 2))
    voltage_margin = min(
        bus.maximum_voltage - magnitude
        for bus, magnitude in zip(case.buses, magnitudes, strict=True)
    )
    feasible = solution.converged and voltage_margin >= 0.0
    return PlacementEvaluation(
        placement=placement,
        feasible=feasible,
        score=voltage_deviation,
        voltage_margin=float(voltage_margin),
        metrics={
            "voltage_deviation": voltage_deviation,
            "iterations": float(solution.iterations),
            "max_mismatch": float(solution.max_mismatch or 0.0),
        },
        details=solution,
    )