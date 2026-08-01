"""Internal numerical solution state shared by AC power-flow algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from o_grid.acpf.results import IterationPowerFlowResult


@dataclass(slots=True)
class NumericalSolution:
    voltage: np.ndarray
    converged: bool = False
    diverged: bool = False
    iterations: int = 0
    max_mismatch: float | None = None
    trace: list[IterationPowerFlowResult] = field(default_factory=list)
