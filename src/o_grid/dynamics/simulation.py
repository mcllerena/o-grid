"""Reduced-order transient and small-signal stability analysis."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
from infrasys import System
from scipy.integrate import solve_ivp

from o_grid.acpf import NewtonRaphsonPowerFlow
from o_grid.acpf.results import ACPowerFlowResult, PowerFlowRun
from o_grid.dynamics.evt_parser import DynamicContingency, EvtFile, EvtFileParser
from o_grid.dynamics.models import (
    StabilityConfig,
    StabilityResult,
    SwingMachine,
)
from o_grid.dynamics.parse_dyn import DynFile, DynFileParser
from o_grid.statics import Generator, NtwFileParser
from o_grid.units import get_magnitude

if TYPE_CHECKING:
    from o_grid.acpf.solver import PowerFlowSolver


class StabilityStudy:
    """Run a power flow followed by a reduced-order stability study.

    The current engine uses the classical swing equation for each synchronous
    machine described by an ``SMxx`` record in the DYN file. AVR, governor, PSS,
    inverter and detailed network algebraic states remain extension points for a
    future full-order model.
    """

    def __init__(
        self,
        network: str | Path | System,
        dynamic_file: str | Path | DynFile,
        *,
        event_file: str | Path | EvtFile | None = None,
        contingency: int | str | None = None,
        config: StabilityConfig | None = None,
        power_flow_solver: PowerFlowSolver | None = None,
    ) -> None:
        self.config = config or StabilityConfig()
        self.network_source = Path(network) if isinstance(network, (str, Path)) else None
        self.dynamic_source = (
            Path(dynamic_file) if isinstance(dynamic_file, (str, Path)) else dynamic_file.source
        )
        self.system = (
            NtwFileParser(self.network_source).system
            if self.network_source is not None
            else cast(System, network)
        )
        self.dynamic_file = (
            DynFileParser(dynamic_file).file
            if isinstance(dynamic_file, (str, Path))
            else dynamic_file
        )
        self.event_file = (
            EvtFileParser(event_file).file if isinstance(event_file, (str, Path)) else event_file
        )
        self.contingency = self._select_contingency(contingency)
        self.power_flow_solver = cast(
            "PowerFlowSolver",
            power_flow_solver or NewtonRaphsonPowerFlow(max_control_passes=0),
        )
        self.power_flow: PowerFlowRun | None = None

    def run_power_flow(self) -> PowerFlowRun:
        """Solve the static NTW network and retain its solved operating point."""
        self.power_flow = self.power_flow_solver.run(self.system)
        if not self.power_flow.result.converged:
            raise RuntimeError("Power flow did not converge; stability initialization aborted")
        return self.power_flow

    def run(self) -> StabilityResult:
        """Run the power flow, initialize machines, and integrate the swing equations."""
        power_flow = self.power_flow or self.run_power_flow()
        machines = self._build_machines(power_flow.result)
        if not machines:
            raise ValueError("No synchronous-machine parameters found in the DYN file")

        time = np.arange(
            0.0, self.config.duration + self.config.time_step / 2, self.config.time_step
        )
        initial_state = np.array(
            [value for machine in machines for value in (machine.initial_angle, 0.0)], dtype=float
        )
        solution = solve_ivp(
            self._derivatives,
            (0.0, self.config.duration),
            initial_state,
            t_eval=time,
            args=(machines,),
            rtol=1e-7,
            atol=1e-9,
        )
        if not solution.success:
            raise RuntimeError(f"Dynamic simulation failed: {solution.message}")

        rotor_angles = {
            machine.bus_id: solution.y[2 * index] for index, machine in enumerate(machines)
        }
        speed_deviations = {
            machine.bus_id: solution.y[2 * index + 1] for index, machine in enumerate(machines)
        }
        electrical_power = {
            machine.bus_id: self._electrical_power(solution.y[2 * index], machine, time)
            for index, machine in enumerate(machines)
        }
        eigenvalues = self.small_signal_eigenvalues(machines)
        stable = bool(
            np.all(eigenvalues.real < 0)
            and max(float(np.max(np.abs(values))) for values in rotor_angles.values()) < math.pi
        )
        return StabilityResult(
            time=solution.t,
            rotor_angles=rotor_angles,
            speed_deviations=speed_deviations,
            electrical_power=electrical_power,
            eigenvalues=eigenvalues,
            machines=tuple(machines),
            power_flow=power_flow.result,
            stable=stable,
            source=self.dynamic_source,
        )

    def small_signal_eigenvalues(self, machines: list[SwingMachine] | None = None) -> np.ndarray:
        """Return eigenvalues of the linearized independent swing equations."""
        if machines is None:
            if self.power_flow is None:
                self.run_power_flow()
            assert self.power_flow is not None
            machines = self._build_machines(self.power_flow.result)
        eigenvalues: list[complex] = []
        for machine in machines:
            synchronizing = machine.power_angle_limit * math.cos(machine.initial_angle)
            damping = machine.damping / (2.0 * machine.inertia)
            stiffness = synchronizing / (2.0 * machine.inertia)
            eigenvalues.extend(np.roots([1.0, damping, stiffness]).astype(complex))
        return np.array(eigenvalues, dtype=complex)

    def _build_machines(self, power_flow: ACPowerFlowResult) -> list[SwingMachine]:
        solved_angles = {bus.id: bus.angle_rad for bus in power_flow.buses}
        generators = {
            _number(generator): generator
            for generator in self.system.get_components(Generator)
            if _number(generator) is not None
        }
        machines: list[SwingMachine] = []
        for model in self.dynamic_file.models:
            if not model.model.upper().startswith("SM") or not model.records:
                continue
            bus_id = _integer(model.records[0].values[0])
            generator = generators.get(bus_id)
            if generator is None or bus_id not in solved_angles:
                continue
            machine_record = next(
                (record for record in model.records[1:] if len(record.values) >= 15), None
            )
            if machine_record is None:
                continue
            inertia = max(abs(_float(machine_record.values[13], 1.0)), 0.05)
            damping = max(abs(_float(machine_record.values[14], 0.0)), 0.0)
            mechanical_power = (
                _magnitude(getattr(generator, "active_generation", None)) / power_flow.base_mva
            )
            initial_angle = solved_angles[bus_id]
            sine = max(abs(math.sin(initial_angle)), 0.1)
            power_angle_limit = max(abs(mechanical_power) / sine, abs(mechanical_power) * 1.2, 0.1)
            machines.append(
                SwingMachine(
                    bus_id=bus_id,
                    model=model.model,
                    inertia=inertia,
                    damping=damping,
                    mechanical_power=mechanical_power,
                    power_angle_limit=power_angle_limit,
                    initial_angle=initial_angle,
                )
            )
        return machines

    def _derivatives(
        self, time: float, state: np.ndarray, machines: list[SwingMachine]
    ) -> np.ndarray:
        derivatives = np.zeros_like(state)
        factor = self._network_factor(time)
        for index, machine in enumerate(machines):
            angle = state[2 * index]
            speed = state[2 * index + 1]
            electrical = factor * machine.power_angle_limit * math.sin(angle)
            derivatives[2 * index] = speed
            derivatives[2 * index + 1] = (
                machine.mechanical_power - electrical - machine.damping * speed
            ) / (2.0 * machine.inertia)
        return derivatives

    def _electrical_power(
        self, angle: np.ndarray, machine: SwingMachine, time: np.ndarray
    ) -> np.ndarray:
        factors = np.array([self._network_factor(value) for value in time])
        return factors * machine.power_angle_limit * np.sin(angle)

    def _network_factor(self, time: float) -> float:
        if self.contingency is None:
            if self.config.fault_time <= time < self.config.clearing_time:
                return self.config.fault_factor
            return self.config.post_fault_factor

        factor = self.config.post_fault_factor
        for event in self.contingency.events:
            if event.event_time > time:
                break
            if event.event_type in {3, 4}:
                factor = self.config.fault_factor
            elif event.event_type in {5, 6, 8}:
                factor = self.config.post_fault_factor
            elif event.event_type in {7, 9, 10, 11}:
                factor = min(factor, self.config.post_fault_factor * 0.8)
        return factor

    def _select_contingency(self, selector: int | str | None) -> DynamicContingency | None:
        if self.event_file is None:
            return None
        if selector is None:
            candidates = [item for item in self.event_file.contingencies if item.events]
            return candidates[0] if candidates else None
        for item in self.event_file.contingencies:
            if item.number == selector or item.identifier.strip() == str(selector).strip():
                return item
        raise ValueError(f"Contingency {selector!r} was not found in {self.event_file.source}")


def _number(component: object) -> int | None:
    value = getattr(component, "number", getattr(component, "bus_id", None))
    return _integer(value) if value is not None else None


def _integer(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected a numeric bus identifier, got {value!r}") from exc


def _float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _magnitude(value: object) -> float:
    if value is None:
        return 0.0
    return float(get_magnitude(value))
