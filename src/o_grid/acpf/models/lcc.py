"""Line-commutated converter injections for the AC network model."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(slots=True)
class LCCInjection:
    bus: int
    active_mw: float
    reactive_mvar: float


def build_lcc_injections(
    components_by_block: Mapping[str, Sequence[object]],
) -> list[LCCInjection]:
    """Build fixed initial AC terminal injections from paired DCNV and DCCV records."""
    controls = {
        int(_values(component).get("number") or 0): _values(component)
        for component in components_by_block.get("DCCV", [])
    }
    injections: list[LCCInjection] = []
    for converter in components_by_block.get("DCNV", []):
        values = _values(converter)
        control = controls.get(int(values.get("number") or 0), {})
        if control.get("converter_control_type") != "P":
            continue
        power = float(control.get("specified_value") or 0.0)
        mode = str(values.get("mode") or "R").upper()
        active = power if mode == "I" else -power
        angle = math.radians(float(control.get("converter_angle") or 0.0))
        reactive = -abs(power) * math.tan(angle)
        injections.append(
            LCCInjection(
                bus=int(values.get("ac_bus") or 0),
                active_mw=active,
                reactive_mvar=reactive,
            )
        )
    return injections


def _values(component: object) -> dict:
    ext = getattr(component, "ext", {})
    return ext.get("pwf_values", {}) if isinstance(ext, dict) else {}
