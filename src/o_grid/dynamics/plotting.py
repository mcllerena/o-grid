"""Plotting helpers for stability-study results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from o_grid.dynamics.models import StabilityResult


def plot_stability_result(result: StabilityResult) -> Figure:
    """Plot rotor angles, speed deviations, and electrical power trajectories."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Plotting requires matplotlib; install the project's plotting dependencies"
        ) from exc

    figure, axes = plt.subplots(3, 1, sharex=True, figsize=(10, 8), constrained_layout=True)
    _plot_series(axes[0], result.time, result.rotor_angles, "Rotor angle (rad)")
    _plot_series(axes[1], result.time, result.speed_deviations, "Speed deviation (rad/s)")
    _plot_series(axes[2], result.time, result.electrical_power, "Electrical power (pu)")
    axes[2].set_xlabel("Time (s)")
    figure.suptitle(f"Transient stability: {'stable' if result.stable else 'unstable'}")
    return figure


def _plot_series(axes: Axes, time: object, series: Mapping[int, object], ylabel: str) -> None:
    for bus_id, values in series.items():
        axes.plot(time, values, label=f"Bus {bus_id}")
    axes.set_ylabel(ylabel)
    axes.grid(True, alpha=0.3)
    axes.legend(loc="best")
