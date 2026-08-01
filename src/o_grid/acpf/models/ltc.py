"""Load tap changer voltage-control updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from o_grid.acpf.models.case import PowerFlowCase


def adjust_ltc_taps(case: PowerFlowCase, voltage: np.ndarray) -> bool:
    """Move bounded LTC taps toward their controlled-bus voltage targets."""
    indices = case.bus_index
    changed = False
    for branch in case.branches:
        if (
            branch.controlled_bus is None
            or branch.minimum_tap <= 0.0
            or branch.maximum_tap <= branch.minimum_tap
        ):
            continue
        control_voltage = abs(voltage[indices[branch.controlled_bus]])
        voltage_error = branch.target_voltage - control_voltage
        if abs(voltage_error) < 1e-3:
            continue
        direction = 1.0 if branch.controlled_bus == branch.from_bus else -1.0
        step = float(np.clip(direction * 0.5 * voltage_error, -0.01, 0.01))
        target = float(np.clip(branch.tap + step, branch.minimum_tap, branch.maximum_tap))
        if abs(target - branch.tap) <= 1e-6:
            continue
        branch.tap = target
        changed = True
    return changed
