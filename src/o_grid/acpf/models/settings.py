"""Case-driven AC power-flow settings derived from PWF options and constants."""

from __future__ import annotations

import math
from dataclasses import dataclass

from o_grid.models.control import PROGRAM_CONSTANT_DEFAULTS
from o_grid.models.enums import OptionState
from o_grid.parser import ParsedAnaredeSystem
from o_grid.units import get_magnitude


@dataclass(slots=True, frozen=True)
class PowerFlowSettings:
    base_mva: float
    active_tolerance: float
    reactive_tolerance: float
    control_tolerance: float
    max_iterations: int
    voltage_divergence_min: float
    voltage_divergence_max: float
    max_angle_step: float
    max_voltage_step: float
    max_csc_step: float
    low_impedance_threshold: float
    options: frozenset[str]

    def enabled(self, option: str) -> bool:
        return option.strip().upper() in self.options


def build_power_flow_settings(
    parsed: ParsedAnaredeSystem,
    *,
    tolerance: float | None = None,
    max_iterations: int | None = None,
) -> PowerFlowSettings:
    """Build numerical settings from typed DCTE and DOPC components."""
    constants = {
        str(getattr(component, "mnemonic", "")).strip().upper(): _magnitude(
            getattr(component, "value", None)
        )
        for component in parsed.components_by_block.get("DCTE", [])
        if getattr(component, "mnemonic", None)
    }

    def value(mnemonic: str) -> float:
        default = float(PROGRAM_CONSTANT_DEFAULTS[mnemonic])
        return constants.get(mnemonic, default)

    base_mva = value("BASE")
    options = frozenset(
        str(getattr(component, "option", "")).strip().upper()
        for component in parsed.components_by_block.get("DOPC", [])
        if getattr(component, "option", None)
        and getattr(component, "state", OptionState.ACTIVATED) == OptionState.ACTIVATED
    )
    return PowerFlowSettings(
        base_mva=base_mva,
        active_tolerance=tolerance if tolerance is not None else value("TEPA") / base_mva,
        reactive_tolerance=tolerance if tolerance is not None else value("TEPR") / base_mva,
        control_tolerance=value("TLVC") * 0.01,
        max_iterations=max_iterations if max_iterations is not None else int(value("ACIT")),
        voltage_divergence_min=value("VDVN") * 0.01,
        voltage_divergence_max=value("VDVM") * 0.01,
        max_angle_step=max(math.radians(5.0), abs(value("ASTP"))),
        max_voltage_step=value("VSTP") * 0.01,
        max_csc_step=value("CSTP") * 0.01,
        low_impedance_threshold=max(2.000001e-4, value("ZMIN") * 0.01),
        options=options,
    )


def _magnitude(value: object) -> float:
    magnitude = get_magnitude(value)
    return float(magnitude)
