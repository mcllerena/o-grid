"""MATPOWER ``.m`` parser and in-memory conversion to an infrasys System."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from infrasys import Component
from loguru import logger

from o_grid.models import BLOCK_BASE_CLASSES
from o_grid.models.m_models import (
    ACBuses,
    Branch,
    DCLines,
    Generators,
    ProgramConstants,
    branch_block,
)
from o_grid.statics.pwf_parser import ParsedAnaredeSystem
from o_grid.system import AnaredeSystem

_matpowercaseframes: ModuleType | None
try:
    _matpowercaseframes = importlib.import_module("matpowercaseframes")
except ImportError:  # pragma: no cover
    _matpowercaseframes = None

CASE_FRAMES_CLS: Any | None = (
    _matpowercaseframes.CaseFrames if _matpowercaseframes is not None else None
)


class MatpowerInfrasysParser:
    """Parse MATPOWER ``.m`` cases and populate an infrasys ``System``."""

    def __init__(self, system_name: str = "MATPOWER", base_mva: float | None = None) -> None:
        self.system_name = system_name
        self.base_mva = base_mva

    def parse(self, pwf_path: Path | str) -> ParsedAnaredeSystem:
        if CASE_FRAMES_CLS is None:  # pragma: no cover - only reachable when dep is missing
            raise ImportError("matpowercaseframes is required to parse MATPOWER cases")
        source = Path(pwf_path)
        frames = CASE_FRAMES_CLS(source)
        frames_any: Any = frames
        base_mva = self.base_mva or float(frames_any.baseMVA)

        bus_records = frames_any.bus.to_dict("records")
        gen_records = frames_any.gen.to_dict("records")
        buses, areas = ACBuses(bus_records, gen_records, base_mva=base_mva)

        components_by_block: dict[str, list[Component]] = {
            "DBAR": list(buses),
            "DLIN": [],
            "DLIN_TRANSFORMER": [],
            "DLIN_PHASE_SHIFT": [],
            "DLIN_SWITCH": [],
            "DGER": cast(list[Component], list(Generators(gen_records))),
            "DCTE": cast(list[Component], list(ProgramConstants(base_mva))),
        }
        for branch in Branch(frames_any.branch.to_dict("records"), base_mva=base_mva):
            components_by_block[branch_block(branch)].append(cast(Component, branch))

        dcline = getattr(frames_any, "dcline", None)
        if dcline is not None and len(dcline):
            for block, block_components in DCLines(dcline.to_dict("records")).items():
                components_by_block[block] = cast(list[Component], list(block_components))

        system = AnaredeSystem(name=self.system_name)
        for area in areas:
            system.add_component(area)
        for block in (
            "DBAR",
            "DGER",
            "DCTE",
            "DLIN",
            "DLIN_TRANSFORMER",
            "DLIN_PHASE_SHIFT",
            "DLIN_SWITCH",
            "DCBA",
            "DCNV",
            "DCCV",
            "DELO",
            "DCLI",
        ):
            for component in components_by_block.get(block, []):
                system.add_component(component)

        populated = {k: v for k, v in components_by_block.items() if v}
        system.description = f"MATPOWER case: {source.name}"
        system.attach_parse_context(source, populated, dict(BLOCK_BASE_CLASSES))
        total = sum(1 for _ in system._component_mgr.iter_all())
        logger.success("Successfully parsed {} MATPOWER component(s).", total)
        return ParsedAnaredeSystem(
            source=source,
            system=system,
            components_by_block=populated,
            component_classes=dict(BLOCK_BASE_CLASSES),
        )


def parse_matpower_system(
    pwf_path: Path | str,
    system_name: str = "MATPOWER",
    base_mva: float | None = None,
) -> ParsedAnaredeSystem:
    """Parse a MATPOWER ``.m`` case into a populated infrasys ``System``."""
    return MatpowerInfrasysParser(system_name=system_name, base_mva=base_mva).parse(pwf_path)
