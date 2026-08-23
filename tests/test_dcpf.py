from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from infrasys import System

from o_grid.acpf.models import build_power_flow_case
from o_grid.dcpf import DCPowerFlow
from o_grid.dcpf.solver import (
    _as_parsed_system,
    _build_dc_matrix,
    _calculate_lossless_branch_results,
    _phase_shift_injections,
)
from o_grid.parser import AnaredeInfrasysParser

DATA = Path(__file__).parent / "data" / "pwf"


def test_dcpf_solves_pwf_with_lossless_results() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = DCPowerFlow(tolerance=1e-7).run(parsed)

    assert run.result.converged is True
    assert run.result.diverged is False
    assert run.result.solver == "dc"
    assert run.result.iterations == 1
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch < 1e-8
    assert len(run.result.iteration_trace) == 1
    assert run.result.iteration_trace[0].iteration == 0
    assert len(run.result.buses) == 9
    assert len(run.result.branches) == 10
    assert parsed.system.power_flow_results is not None


def test_dcpf_can_report_lossy_branch_flows() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = DCPowerFlow(lossy_flows=True).run(parsed)

    assert run.result.converged is True
    assert len(run.result.branches) == 10
    assert any(abs(branch.active_loss_mw) > 0.0 for branch in run.result.branches)


def test_dcpf_constructor_solves_and_returns_system() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    solved = DCPowerFlow(parsed.system)

    assert isinstance(solved, System)
    assert solved is parsed.system
    assert solved.power_flow_results is not None
    assert solved.power_flow_results.information.converged is True


def test_dcpf_system_source_is_supported() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    run = DCPowerFlow().run(parsed.system)

    assert run.result.converged is True
    assert run.system is parsed.system


def test_dcpf_matrix_and_phase_shift_injections_are_consistent() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    case = build_power_flow_case(parsed)

    matrix = _build_dc_matrix(case)
    phase_shift = _phase_shift_injections(case)

    assert matrix.shape == (9, 9)
    assert np.allclose(matrix.toarray(), matrix.toarray().T)
    assert phase_shift.shape == (9,)
    assert np.isclose(phase_shift.sum(), 0.0)


def test_dcpf_rejects_system_without_reference_bus() -> None:
    case = SimpleNamespace(slack_indices=np.array([], dtype=np.int64))

    with pytest.raises(ValueError, match="no reference bus"):
        from o_grid.dcpf.solver import _solve_angles

        _solve_angles(case)


def test_dcpf_parsed_system_conversion_is_idempotent() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")

    assert _as_parsed_system(parsed, None) is parsed
    assert _as_parsed_system(parsed.system, None).system is parsed.system


def test_dcpf_lossless_branch_results_have_zero_losses() -> None:
    parsed = AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")
    case = build_power_flow_case(parsed)
    angles = np.zeros(len(case.buses))

    results = _calculate_lossless_branch_results(case, angles)

    assert all(result.active_loss_mw == 0.0 for result in results)
    assert all(result.reactive_from_mvar == 0.0 for result in results)
