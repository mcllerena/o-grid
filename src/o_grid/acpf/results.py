"""Typed AC power-flow results and infrasys result application."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel

from o_grid.models import ACBus
from o_grid.parser import ParsedAnaredeSystem
from o_grid.units import ActivePower, Angle, PerUnit, ReactivePower


class BusPowerFlowResult(BaseModel):
    id: int
    name: str
    voltage_pu: float
    angle_rad: float
    active_injection_pu: float
    reactive_injection_pu: float


class BranchPowerFlowResult(BaseModel):
    from_bus: int
    to_bus: int
    circuit: int
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    loading_percent: float
    active_loss_mw: float
    reactive_loss_mvar: float


class IterationPowerFlowResult(BaseModel):
    iteration: int
    max_dp: float
    max_dq: float
    max_control_residual: float
    max_residual: float
    max_step: float


class ACPowerFlowResult(BaseModel):
    solver: str
    converged: bool
    diverged: bool
    iterations: int
    max_mismatch: float | None
    fallback_used: bool = False
    base_mva: float
    iteration_trace: list[IterationPowerFlowResult]
    buses: list[BusPowerFlowResult]
    branches: list[BranchPowerFlowResult]


@dataclass(slots=True)
class PowerFlowRun:
    parsed: ParsedAnaredeSystem
    result: ACPowerFlowResult
    stdout: str

    @property
    def system(self):
        return self.parsed.system


def apply_power_flow_result(parsed: ParsedAnaredeSystem, result: ACPowerFlowResult) -> None:
    """Attach solved bus states and branch flows to the parsed infrasys system."""
    buses = {
        _integer_key(getattr(bus, "number", None)): bus
        for bus in parsed.components_by_block.get("DBAR", [])
    }
    for solved in result.buses:
        bus = buses.get(solved.id)
        if not isinstance(bus, ACBus):
            continue
        bus.solved_voltage = PerUnit(solved.voltage_pu, "pu")
        bus.solved_angle = Angle(math.degrees(solved.angle_rad), "degree")
        bus.active_power_injection = ActivePower(solved.active_injection_pu * result.base_mva, "MW")
        bus.reactive_power_injection = ReactivePower(
            solved.reactive_injection_pu * result.base_mva, "MVAr"
        )
        bus.ext["power_flow"] = solved.model_dump()

    branches: dict[tuple[int, int, int], list[object]] = {}
    for block in (
        "DLIN",
        "DLIN_TAP",
        "DLIN_PHASE_SHIFT",
        "DLIN_TRANSFORMER",
        "DLIN_SWITCH",
    ):
        for branch in parsed.components_by_block.get(block, []):
            key = _branch_key(branch)
            branches.setdefault(key, []).append(branch)

    for solved in result.branches:
        key = (solved.from_bus, solved.to_bus, solved.circuit)
        reverse_key = (solved.to_bus, solved.from_bus, solved.circuit)
        for branch in branches.get(key, branches.get(reverse_key, [])):
            ext = getattr(branch, "ext", None)
            if isinstance(ext, dict):
                ext["power_flow"] = solved.model_dump()


def _branch_key(branch: object) -> tuple[int, int, int]:
    from_bus = getattr(branch, "from_bus", None)
    to_bus = getattr(branch, "to_bus", None)
    return (
        _integer_key(getattr(from_bus, "number", from_bus)),
        _integer_key(getattr(to_bus, "number", to_bus)),
        _integer_key(getattr(branch, "line_circuit", None), default=1),
    )


def _integer_key(value: object, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default
