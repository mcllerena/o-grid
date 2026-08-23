"""Data models for reduced-order transient-stability studies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from o_grid.acpf.results import ACPowerFlowResult


@dataclass(frozen=True, slots=True)
class SwingMachine:
    """Classical synchronous-machine parameters in per-unit form."""

    bus_id: int
    model: str
    inertia: float
    damping: float
    mechanical_power: float
    power_angle_limit: float
    initial_angle: float


@dataclass(frozen=True, slots=True)
class StabilityConfig:
    """Numerical settings and a temporary network disturbance definition."""

    duration: float = 10.0
    time_step: float = 0.01
    fault_time: float = 1.0
    clearing_time: float = 1.1
    fault_factor: float = 0.2
    post_fault_factor: float = 1.0
    frequency_hz: float = 60.0

    def __post_init__(self) -> None:
        if self.duration <= 0 or self.time_step <= 0:
            raise ValueError("duration and time_step must be positive")
        if not 0 <= self.fault_time <= self.clearing_time <= self.duration:
            raise ValueError("fault_time and clearing_time must be within duration")
        if not 0 < self.fault_factor <= 1 or not 0 < self.post_fault_factor <= 1:
            raise ValueError("fault factors must be in the interval (0, 1]")
        if self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")


@dataclass(slots=True)
class StabilityResult:
    """Time-domain trajectories and small-signal results for a study."""

    time: np.ndarray
    rotor_angles: dict[int, np.ndarray]
    speed_deviations: dict[int, np.ndarray]
    electrical_power: dict[int, np.ndarray]
    eigenvalues: np.ndarray
    machines: tuple[SwingMachine, ...]
    power_flow: ACPowerFlowResult
    stable: bool
    source: Path | None = None

    @property
    def maximum_angle(self) -> float:
        """Return the largest absolute rotor angle in radians."""
        if not self.rotor_angles:
            return 0.0
        return max(float(np.max(np.abs(values))) for values in self.rotor_angles.values())

    @property
    def damping_ratios(self) -> np.ndarray:
        """Return modal damping ratios for the reported eigenvalues."""
        magnitudes = np.abs(self.eigenvalues)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratios = -self.eigenvalues.real / magnitudes
        return np.nan_to_num(ratios)


@dataclass(frozen=True, slots=True)
class StabilityStudyInputs:
    """Paths used to construct a study from an NTW and a DYN file."""

    network_path: Path
    dynamic_path: Path
