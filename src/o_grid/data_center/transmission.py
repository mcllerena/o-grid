"""Materialize selected transmission expansion projects for AC validation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from o_grid.acpf.models.case import BranchData, PowerFlowCase
from o_grid.data_center.models import TransmissionExpansionProject


def apply_transmission_expansion(
    case: PowerFlowCase,
    projects: Iterable[TransmissionExpansionProject],
) -> PowerFlowCase:
    """Return a case with the selected candidate branches appended.

    The input case is not mutated. Candidate projects must reference buses
    already present in the parsed network; their electrical parameters are
    copied directly into fixed branches for continuous ACOPF validation.
    """
    bus_numbers = {bus.number for bus in case.buses}
    branches = list(case.branches)
    used_circuits = {(branch.from_bus, branch.to_bus, branch.circuit) for branch in branches}
    for project in projects:
        if project.from_bus not in bus_numbers or project.to_bus not in bus_numbers:
            raise ValueError(f"transmission project {project.name!r} references an unknown bus")
        key = (project.from_bus, project.to_bus, project.circuit)
        if key in used_circuits:
            raise ValueError(
                f"transmission project {project.name!r} duplicates an existing circuit"
            )
        branches.append(
            BranchData(
                from_bus=project.from_bus,
                to_bus=project.to_bus,
                circuit=project.circuit,
                resistance=project.resistance,
                reactance=project.reactance,
                charging=project.charging,
                tap=1.0,
                phase_shift=0.0,
                rating=project.rating_mva,
            )
        )
        used_circuits.add(key)
    return replace(case, branches=branches)


def projects_built_by_year(
    projects: Iterable[TransmissionExpansionProject],
    built: dict[tuple[str, int], float],
    year: int,
) -> list[TransmissionExpansionProject]:
    """Select projects whose expansion-plan build decision is active by ``year``."""
    return [
        project
        for project in projects
        if any(
            built.get((project.name, build_year), 0.0) > 0.5
            for build_year in range(1, year + 1)
        )
    ]