from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

from o_grid.dynamics import (
    DynamicContingency,
    DynamicEvent,
    EvtFileParser,
    StabilityConfig,
    StabilityResult,
    StabilityStudy,
    SwingMachine,
    plot_stability_result,
)
from o_grid.dynamics.simulation import _float, _integer, _magnitude

matplotlib.use("Agg")

DATA = Path(__file__).parent / "data"
NTW_PATH = DATA / "ntw" / "9bus.ntw"
DYN_PATH = DATA / "dyn" / "9bus.dyn"
EVT_PATH = DATA / "evt" / "9bus.evt"


def test_stability_config_validates_numeric_settings() -> None:
    with pytest.raises(ValueError, match="duration and time_step"):
        StabilityConfig(duration=0.0)
    with pytest.raises(ValueError, match="fault_time and clearing_time"):
        StabilityConfig(fault_time=2.0, clearing_time=1.0)
    with pytest.raises(ValueError, match="fault factors"):
        StabilityConfig(fault_factor=0.0)
    with pytest.raises(ValueError, match="frequency_hz"):
        StabilityConfig(frequency_hz=0.0)


def test_stability_result_properties() -> None:
    machine = SwingMachine(1, "SM04", 5.0, 1.0, 0.5, 1.0, 0.2)
    result = StabilityResult(
        time=np.array([0.0, 1.0]),
        rotor_angles={1: np.array([0.2, -0.4])},
        speed_deviations={1: np.array([0.0, 0.1])},
        electrical_power={1: np.array([0.2, 0.3])},
        eigenvalues=np.array([-0.1 + 1j, -0.1 - 1j]),
        machines=(machine,),
        power_flow=None,
        stable=True,
    )

    assert result.maximum_angle == pytest.approx(0.4)
    assert np.all(result.damping_ratios == pytest.approx(0.1 / np.sqrt(1.01)))


def test_stability_result_empty_angles_have_zero_maximum() -> None:
    result = StabilityResult(
        time=np.array([]),
        rotor_angles={},
        speed_deviations={},
        electrical_power={},
        eigenvalues=np.array([], dtype=complex),
        machines=(),
        power_flow=None,
        stable=True,
    )

    assert result.maximum_angle == 0.0
    assert result.damping_ratios.size == 0


def test_stability_study_runs_reduced_order_simulation() -> None:
    study = StabilityStudy(
        NTW_PATH,
        DYN_PATH,
        config=StabilityConfig(duration=0.2, time_step=0.1, fault_time=0.05, clearing_time=0.1),
    )

    result = study.run()

    assert result.time.size == 3
    assert len(result.machines) == 3
    assert set(result.rotor_angles) == {1, 2, 3}
    assert result.eigenvalues.size == 6
    assert result.power_flow.converged is True
    assert result.source == DYN_PATH
    assert study.power_flow is not None
    assert study.small_signal_eigenvalues().size == 6


def test_stability_study_uses_event_network_factors() -> None:
    study = StabilityStudy(
        NTW_PATH,
        DYN_PATH,
        event_file=EVT_PATH,
        contingency=2,
        config=StabilityConfig(duration=2.0, time_step=0.1),
    )

    assert study.contingency is not None
    assert study._network_factor(0.0) == pytest.approx(1.0)
    assert study._network_factor(0.3) == pytest.approx(0.2)
    assert study._network_factor(0.4) == pytest.approx(0.8)


def test_stability_study_selects_contingency_by_identifier() -> None:
    study = StabilityStudy(
        NTW_PATH,
        DYN_PATH,
        event_file=EVT_PATH,
        contingency="Steady state",
        config=StabilityConfig(duration=2.0),
    )

    assert study.contingency is not None
    assert study.contingency.number == 1

    with pytest.raises(ValueError, match="was not found"):
        StabilityStudy(NTW_PATH, DYN_PATH, event_file=EVT_PATH, contingency="missing")


def test_stability_study_derivatives_and_electrical_power() -> None:
    study = StabilityStudy(NTW_PATH, DYN_PATH, config=StabilityConfig(duration=2.0))
    machine = SwingMachine(1, "SM", 5.0, 1.0, 0.2, 1.0, 0.1)
    state = np.array([0.1, 0.0])
    time = np.array([0.0, 0.5])

    derivatives = study._derivatives(0.0, state, [machine])
    electrical = study._electrical_power(np.array([0.1, 0.2]), machine, time)

    assert derivatives[0] == 0.0
    assert derivatives[1] > 0.0
    assert electrical.shape == (2,)
    assert electrical[1] > electrical[0]


def test_plot_stability_result_creates_three_axis_figure() -> None:
    result = StabilityResult(
        time=np.array([0.0, 1.0]),
        rotor_angles={1: np.array([0.0, 0.1])},
        speed_deviations={1: np.array([0.0, 0.2])},
        electrical_power={1: np.array([0.5, 0.6])},
        eigenvalues=np.array([-1.0 + 0j]),
        machines=(),
        power_flow=None,
        stable=False,
    )

    figure = plot_stability_result(result)

    assert len(figure.axes) == 3
    assert figure.axes[0].get_ylabel() == "Rotor angle (rad)"
    assert figure.axes[2].get_xlabel() == "Time (s)"
    figure.clf()


def test_evt_parser_handles_empty_and_malformed_files(tmp_path: Path) -> None:
    empty = tmp_path / "empty.evt"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        EvtFileParser(empty)

    outside = tmp_path / "outside.evt"
    outside.write_text("1.0 /\n3 1 2 1 0 0 0 A B 0 /\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside a contingency"):
        EvtFileParser(outside)


def test_dynamic_event_and_contingency_values_are_structured() -> None:
    event = DynamicEvent(3, 1, 2, "1", 0.0, 0.0, 0.25, "A", "B", 0.0, 1, "raw")
    contingency = DynamicContingency(1, "case", (event,), 1, "raw")

    assert event.event_time == 0.25
    assert contingency.events == (event,)


def test_simulation_numeric_helpers_use_defaults_and_units() -> None:
    assert _integer("2.0") == 2
    with pytest.raises(ValueError, match="numeric bus identifier"):
        _integer("bus")
    assert _float("bad", 3.0) == 3.0
    assert _float("1.5", 3.0) == 1.5
    assert _magnitude(None) == 0.0
