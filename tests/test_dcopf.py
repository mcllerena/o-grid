from __future__ import annotations

from pathlib import Path

import pytest

from o_grid.acpf.models import build_power_flow_case
from o_grid.dcopf import DCOPFParameters, DCOptimalPowerFlow
from o_grid.dcopf.solver import (
    _branch_key,
    _cold_b,
    _cold_parameters,
    _dcpf_parameters,
    _hot_parameters,
)
from o_grid.parser import AnaredeInfrasysParser

DATA = Path(__file__).parent / "data" / "pwf"


def _parsed_case():
    return AnaredeInfrasysParser().parse(DATA / "d_9nodes.pwf")


@pytest.mark.parametrize("mode", ["cold_start", "hot_start", "dcpf"])
def test_dcopf_solves_with_each_online_parameterization(mode: str) -> None:
    run = DCOptimalPowerFlow(param_opt=mode, enforce_branch_limits=False).run(_parsed_case())

    assert run.result.converged is True
    assert run.result.diverged is False
    assert run.result.solver == "dcopf"
    assert run.result.iterations == 1
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch < 1e-8
    assert run.result.iteration_trace[0].iteration == 1


def test_dcopf_enforces_branch_limits_by_default() -> None:
    run = DCOptimalPowerFlow(param_opt="cold_start").run(_parsed_case())

    assert run.result.converged is True
    assert all(branch.loading_percent <= 100.0 + 1e-8 for branch in run.result.branches)


def test_dcopf_accepts_parameter_aliases() -> None:
    for alias, expected in {
        "cold": "cold_start",
        "cold-start": "cold_start",
        "hot": "hot_start",
        "hot-start": "hot_start",
        "optimized_dcpf": "dcpf",
        "dc_opf_optimal": "optimal",
    }.items():
        solver = DCOptimalPowerFlow(param_opt=alias)
        assert solver.param_opt == expected


def test_dcopf_rejects_unknown_parameterization() -> None:
    with pytest.raises(ValueError, match="param_opt"):
        DCOptimalPowerFlow(param_opt="unknown")


def test_dcopf_optimal_requires_trained_parameters() -> None:
    with pytest.raises(ValueError, match="requires trained parameters"):
        DCOptimalPowerFlow(param_opt="optimal").run(_parsed_case())


def test_dcopf_optimal_uses_supplied_parameters() -> None:
    parsed = _parsed_case()
    case = build_power_flow_case(parsed)
    cold = _cold_parameters(case)
    parameters = DCOPFParameters(b=cold.b.copy(), gamma=cold.gamma.copy(), rho=cold.rho.copy())

    run = DCOptimalPowerFlow(
        param_opt="optimal",
        parameters=parameters,
        enforce_branch_limits=False,
    ).run(parsed)

    assert run.result.converged is True
    assert run.result.max_mismatch is not None
    assert run.result.max_mismatch < 1e-8


def test_dcopf_parameter_modes_have_expected_coefficients() -> None:
    parsed = _parsed_case()
    case = build_power_flow_case(parsed)
    cold = _cold_parameters(case)
    dcpf = _dcpf_parameters(case)
    hot = _hot_parameters(case, cold)

    assert set(cold.b) == {_branch_key(branch) for branch in case.branches}
    assert all(value == 0.0 for value in cold.gamma.values())
    assert any(cold.b[key] != dcpf.b[key] for key in cold.b)
    assert set(hot.gamma) == {bus.number for bus in case.buses}
    assert set(hot.rho) == set(cold.rho)


def test_dcopf_accepts_constructor_system() -> None:
    parsed = _parsed_case()

    run = DCOptimalPowerFlow(parsed.system, enforce_branch_limits=False).run()

    assert run.system is parsed.system
    assert run.result.converged is True


def test_dcopf_requires_a_source() -> None:
    with pytest.raises(ValueError, match="requires a source"):
        DCOptimalPowerFlow().run()


def test_dcopf_cold_coefficient_rejects_zero_reactance() -> None:
    branch = type("Branch", (), {"from_bus": 1, "to_bus": 2, "reactance": 0.0})()

    with pytest.raises(ValueError, match="zero reactance"):
        _cold_b(branch)
