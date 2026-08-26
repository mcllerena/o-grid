from __future__ import annotations

import pytest

from o_grid.solvers import ClarabelBridge


def test_clarabel_bridge_solves_when_available() -> None:
    bridge = ClarabelBridge()
    if not bridge.available():
        pytest.skip("Julia or the bundled Clarabel environment is unavailable")

    result = bridge.solve(
        {
            "n": 1,
            "m": 1,
            "P": [],
            "q": [0.0],
            "A": [[1, 1, 1.0]],
            "b": [1.0],
            "cones": [{"type": "zero", "dimension": 1}],
        }
    )

    assert result.status in {"Solved", "AlmostSolved", "SOLVED", "ALMOST_SOLVED"}
    assert result.x == pytest.approx([1.0], abs=1.0e-6)