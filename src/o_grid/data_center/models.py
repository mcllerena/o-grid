"""Data models for large-load placement studies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from o_grid.acpf.models import PowerFlowCase


@dataclass(frozen=True, slots=True)
class DataCenterLoad:
    """A load block, with reactive demand derived from its power factor."""

    active_mw: float
    power_factor: float = 0.98
    name: str = "data_center"

    def __post_init__(self) -> None:
        if self.active_mw <= 0.0:
            raise ValueError("active_mw must be positive")
        if not 0.0 < self.power_factor <= 1.0:
            raise ValueError("power_factor must be in the interval (0, 1]")

    @property
    def reactive_mvar(self) -> float:
        """Return lagging reactive demand in MVAr."""
        from math import sqrt

        return self.active_mw * sqrt(1.0 - self.power_factor**2) / self.power_factor


@dataclass(frozen=True, slots=True)
class LoadPlacement:
    """A candidate allocation represented by bus numbers and binary selections."""

    selected_buses: tuple[int, ...]
    load: DataCenterLoad

    def __post_init__(self) -> None:
        if not self.selected_buses:
            raise ValueError("at least one bus must be selected")
        if len(set(self.selected_buses)) != len(self.selected_buses):
            raise ValueError("selected_buses must not contain duplicates")


@dataclass(frozen=True, slots=True)
class PlacementEvaluation:
    """Metrics returned by a placement evaluator."""

    placement: LoadPlacement
    feasible: bool
    score: float
    voltage_margin: float | None = None
    stability_margin: float | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    details: Any = None


PlacementEvaluator = Callable[[PowerFlowCase, LoadPlacement], PlacementEvaluation]


@dataclass(frozen=True, slots=True)
class TransmissionExpansionProject:
    """Candidate AC branch that can be built by the expansion model."""

    name: str
    connection_bus: int
    from_bus: int
    to_bus: int
    resistance: float
    reactance: float
    charging: float
    rating_mva: float
    capacity_mw: float
    investment_cost: float
    available_year: int = 0
    circuit: int = 1

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("transmission project name must not be empty")
        if self.from_bus == self.to_bus:
            raise ValueError("transmission project endpoints must differ")
        if min(self.resistance, self.reactance, self.charging) < 0.0:
            raise ValueError("transmission impedance values must be non-negative")
        if self.rating_mva <= 0.0 or self.capacity_mw <= 0.0:
            raise ValueError("transmission ratings and capacity must be positive")
        if self.investment_cost < 0.0 or self.available_year < 0:
            raise ValueError("transmission cost and available year must be non-negative")


@dataclass(slots=True)
class PlacementStudy:
    """Configuration for a candidate-bus placement study."""

    candidate_buses: tuple[int, ...]
    load: DataCenterLoad
    max_sites: int = 1

    def __post_init__(self) -> None:
        if not self.candidate_buses:
            raise ValueError("candidate_buses must not be empty")
        if len(set(self.candidate_buses)) != len(self.candidate_buses):
            raise ValueError("candidate_buses must not contain duplicates")
        if not 1 <= self.max_sites <= len(self.candidate_buses):
            raise ValueError("max_sites must be between 1 and the number of candidates")


@dataclass(frozen=True, slots=True)
class CapacityExpansionStudy:
    """Multi-period load-site and co-located generation expansion inputs.

    ``cumulative_load_mw_by_year`` contains end-of-year cumulative capacity
    targets, matching ReEDS's ``loadsite_annual`` convention.  Bus numbers are
    the Brazilian network's
    eligibility regions at this model resolution.
    """

    candidate_buses: tuple[int, ...]
    cumulative_load_mw_by_year: Mapping[int, float]
    generation_mw_per_load_mw: float = 1.0
    generation_mvar_per_load_mw: float = 0.0
    capacity_factor: float = 1.0
    max_sites: int | None = None
    max_capacity_mw_by_bus: Mapping[int, float] | None = None
    load_site_cost_by_bus: Mapping[int, float] = field(default_factory=dict)
    generation_cost_by_bus: Mapping[int, float] = field(default_factory=dict)
    interconnection_capacity_mw_by_bus: Mapping[int, float] = field(default_factory=dict)
    interconnection_expansion_cost_by_bus: Mapping[int, float] = field(default_factory=dict)
    max_interconnection_expansion_mw_by_bus: Mapping[int, float] | None = None
    transmission_projects: tuple[TransmissionExpansionProject, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_buses:
            raise ValueError("candidate_buses must not be empty")
        if len(set(self.candidate_buses)) != len(self.candidate_buses):
            raise ValueError("candidate_buses must not contain duplicates")
        if not self.cumulative_load_mw_by_year or any(
            year <= 0 or capacity < 0.0
            for year, capacity in self.cumulative_load_mw_by_year.items()
        ):
            raise ValueError(
                "cumulative_load_mw_by_year must contain non-negative positive years"
            )
        if any(
            earlier > later
            for earlier, later in zip(
                sorted(self.cumulative_load_mw_by_year),
                sorted(self.cumulative_load_mw_by_year)[1:],
                strict=False,
            )
            if self.cumulative_load_mw_by_year[earlier]
            > self.cumulative_load_mw_by_year[later]
        ):
            raise ValueError("cumulative_load_mw_by_year must be non-decreasing")
        if self.generation_mw_per_load_mw < 0.0 or self.generation_mvar_per_load_mw < 0.0:
            raise ValueError("generation ratios must be non-negative")
        if not 0.0 < self.capacity_factor <= 1.0:
            raise ValueError("capacity_factor must be in the interval (0, 1]")
        if self.max_sites is not None and not 1 <= self.max_sites <= len(self.candidate_buses):
            raise ValueError("max_sites must be between 1 and the number of candidates")
        if self.max_capacity_mw_by_bus is not None and any(
            bus not in self.candidate_buses or capacity < 0.0
            for bus, capacity in self.max_capacity_mw_by_bus.items()
        ):
            raise ValueError("max_capacity_mw_by_bus must contain valid non-negative capacities")
        for mapping in (
            self.interconnection_capacity_mw_by_bus,
            self.interconnection_expansion_cost_by_bus,
        ):
            if any(
                bus not in self.candidate_buses or value < 0.0
                for bus, value in mapping.items()
            ):
                raise ValueError("interconnection mappings must contain valid non-negative values")
        if self.max_interconnection_expansion_mw_by_bus is not None and any(
            bus not in self.candidate_buses or capacity < 0.0
            for bus, capacity in self.max_interconnection_expansion_mw_by_bus.items()
        ):
            raise ValueError(
                "max_interconnection_expansion_mw_by_bus must contain valid non-negative capacities"
            )
        project_names = [project.name for project in self.transmission_projects]
        if len(set(project_names)) != len(project_names):
            raise ValueError("transmission project names must be unique")
        if any(
            project.connection_bus not in self.candidate_buses
            for project in self.transmission_projects
        ):
            raise ValueError("transmission projects must connect to candidate buses")


@dataclass(frozen=True, slots=True)
class CapacityExpansionPlan:
    """Solved cumulative load and generation capacities by year and bus."""

    load_capacity_mw: dict[tuple[int, int], float]
    generation_capacity_mw: dict[tuple[int, int], float]
    reactive_generation_capacity_mvar: dict[tuple[int, int], float]
    site_active: dict[int, float]
    interconnection_capacity_mw: dict[tuple[int, int], float] = field(default_factory=dict)
    transmission_built: dict[tuple[str, int], float] = field(default_factory=dict)