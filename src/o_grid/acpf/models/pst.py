"""Phase-shifting transformer static network application."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from o_grid.units import get_magnitude

if TYPE_CHECKING:
    from o_grid.acpf.models.case import BranchData
    from o_grid.models import PhaseShiftingTransformer


def apply_pst_to_branch(component: PhaseShiftingTransformer, branch: BranchData) -> None:
    """Apply the fixed PWF phase and optional impedance overrides used by C++."""
    values = _values(component)
    branch.phase_shift = -math.radians(float(values.get("phase_shift") or 0.0))
    resistance = _magnitude(getattr(component, "r", None))
    reactance = _magnitude(getattr(component, "x", None))
    if abs(resistance) > 0.0 or abs(reactance) > 0.0:
        branch.resistance = resistance * 0.01
        branch.reactance = reactance * 0.01


def _values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}


def _magnitude(value: object) -> float:
    return float(get_magnitude(value)) if value is not None else 0.0
