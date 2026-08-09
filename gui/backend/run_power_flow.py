"""Solve a power-flow case (MATPOWER ``.m`` or ANAREDE ``.pwf``) and print a JSON report.

The GUI spawns this script with the o-grid virtualenv interpreter. All status and
diagnostic output goes to stderr (loguru writes there too); stdout carries exactly
one JSON object that the GUI parses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from o_grid import (  # noqa: E402
    FastDecoupledPowerFlow,
    NewtonRaphsonPowerFlow,
    OptimizationACPowerFlow,
    parse_anarede_system,
    parse_matpower_system,
)

SOLVERS = {
    "newton-raphson": NewtonRaphsonPowerFlow,
    "fast-decoupled": FastDecoupledPowerFlow,
    "optimization": OptimizationACPowerFlow,
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an AC power flow and emit JSON.")
    parser.add_argument("--case", required=True, help="Path to a .m or .pwf case.")
    parser.add_argument("--method", default="newton-raphson", choices=sorted(SOLVERS))
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument(
        "--max-control-passes",
        type=int,
        default=12,
        help="Automatic control passes (LTC taps, switched shunts, reactive limits).",
    )
    parser.add_argument(
        "--objective-function",
        default="minimize_residuals",
        choices=("minimize_residuals", "zero_function", "squared_generation"),
    )
    return parser.parse_args()


def load_case(case_path: str):
    path = Path(case_path)
    suffix = path.suffix.lower()
    if suffix == ".m":
        return parse_matpower_system(path)
    if suffix == ".pwf":
        return parse_anarede_system(path, system_name=path.stem)
    raise ValueError(
        f"Unsupported case type {suffix!r}; expected a MATPOWER .m or ANAREDE .pwf file."
    )


def report_from(parsed, elapsed_seconds: float) -> dict:
    results = parsed.system.power_flow_results
    info = results.information
    return {
        "converged": info.converged,
        "diverged": info.diverged,
        "solver": info.solver,
        "method": info.method or info.solver,
        "iterations": info.iterations,
        "max_mismatch_pu": info.max_mismatch_pu,
        "source_path": info.source_path,
        "base_mva": info.base_mva,
        "convergence_tolerance_pu": info.convergence_tolerance_pu,
        "scheduled_generation_mw": info.scheduled_generation_mw,
        "solved_generation_mw": info.solved_generation_mw,
        "total_load_mw": info.total_load_mw,
        "branch_active_losses_mw": info.branch_active_losses_mw,
        "power_balance_mw": info.power_balance_mw,
        "bus_count": info.bus_count,
        "bus_count_after_reduction": info.bus_count_after_reduction,
        "branch_count": info.branch_count,
        "branch_count_after_reduction": info.branch_count_after_reduction,
        "voltage_upper_violations": info.voltage_upper_violations,
        "voltage_lower_violations": info.voltage_lower_violations,
        "line_flow_overloads": info.line_flow_overloads,
        "elapsed_seconds": elapsed_seconds,
    }


def main() -> int:
    args = parse_arguments()
    started = time.monotonic()
    try:
        parsed = load_case(args.case)
        solver_class = SOLVERS[args.method]
        solver_kwargs = {
            "tolerance": args.tolerance,
            "max_iterations": args.max_iterations,
            "max_control_passes": args.max_control_passes,
        }
        if solver_class is OptimizationACPowerFlow:
            solver_kwargs["objective_function"] = args.objective_function
        solver = solver_class(**solver_kwargs)
        run = solver.run(parsed)
        report = report_from(run.parsed, time.monotonic() - started)
        print(json.dumps(report, indent=2))
        return 0 if report["converged"] else 2
    except Exception as exc:  # noqa: BLE001
        print(f"Backend error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
