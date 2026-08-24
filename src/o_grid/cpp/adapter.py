"""Run the native power-flow executable and adapt its report to o-grid results."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from o_grid.acpf.results import ACPowerFlowResult, BranchPowerFlowResult, BusPowerFlowResult
from o_grid.cpp.ntw2dat import convert as convert_ntw
from o_grid.cpp.pwf2dat import convert as convert_pwf
from o_grid.statics.pwf_parser import ParsedAnaredeSystem


def solve_with_cpp(
    parsed: ParsedAnaredeSystem,
    *,
    solver_name: str,
    tolerance: float | None,
    max_iterations: int,
    print_iterations: bool,
) -> tuple[ACPowerFlowResult, str]:
    source = Path(parsed.source)
    native_case = source.with_suffix(".dat")
    if source.suffix.lower() == ".ntw":
        convert_ntw(source, native_case)
    elif source.suffix.lower() == ".pwf":
        convert_pwf(source, native_case)
    elif source.suffix.lower() != ".dat":
        raise ValueError(f"The C++ backend supports .pwf, .ntw, and .dat inputs, not {source.suffix}")  # noqa: E501

    executable = _executable(solver_name)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as report_file:
        report_path = Path(report_file.name)
    try:
        command = [str(executable), str(native_case), "--save", str(report_path)]
        if tolerance is not None:
            command.append(str(tolerance))
        command.append(str(max_iterations))
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        report = report_path.read_text(encoding="utf-8", errors="replace")
    finally:
        report_path.unlink(missing_ok=True)

    output = completed.stdout + completed.stderr
    if completed.returncode not in (0, 2):
        raise RuntimeError(f"C++ power-flow failed with exit code {completed.returncode}:\n{output}")  # noqa: E501
    result = _parse_report(report, parsed, solver_name)
    if print_iterations:
        print(output, end="")
    return result, output


def _executable(solver_name: str) -> Path:
    root = Path(__file__).resolve().parent
    build = root.parents[2] / ".native-build"
    name = "o_grid_fast_decoupled" if solver_name == "fast-decoupled" else "o_grid_newton"
    executable = build / f"{name}.exe"
    if not executable.exists():
        executable = build / name
    if not executable.exists():
        raise FileNotFoundError(
            f"Native executable not found at {build}. Build it with "
            "cmake -S src/o_grid/cpp -B .native-build && cmake --build .native-build."
        )
    return executable


def _parse_report(report: str, parsed: ParsedAnaredeSystem, solver_name: str) -> ACPowerFlowResult:
    base_mva = _summary_float(report, "Base MVA", 100.0)
    converged = _summary_value(report, "Converged") == "yes"
    iterations = int(_summary_float(report, "Iterations", 0.0))
    mismatch = _summary_float(report, "Max mismatch", 0.0)
    buses = _parse_buses(report, parsed, base_mva)
    branches = _parse_branches(report)
    return ACPowerFlowResult(
        solver=solver_name,
        converged=converged,
        diverged=not converged,
        iterations=iterations,
        max_mismatch=mismatch,
        base_mva=base_mva,
        iteration_trace=[],
        buses=buses,
        branches=branches,
    )


def _parse_buses(report: str, parsed: ParsedAnaredeSystem, base_mva: float) -> list[BusPowerFlowResult]:  # noqa: E501
    loads = {
        int(float(getattr(bus, "number", 0))): (
            _magnitude(getattr(bus, "active_load", None)),
            _magnitude(getattr(bus, "reactive_load", None)),
        )
        for bus in parsed.components_by_block.get("DBAR", [])
    }
    start = report.find("PYOMO_WARM_START_BEGIN")
    end = report.find("PYOMO_WARM_START_END", start)
    if start < 0 or end < 0:
        raise RuntimeError("Native report does not contain PYOMO_WARM_START results")
    results = []
    for line in report[start:end].splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[0] != "BUS":
            continue
        bus_id = int(fields[1])
        active_load, reactive_load = loads.get(bus_id, (0.0, 0.0))
        results.append(
            BusPowerFlowResult(
                id=bus_id,
                name=str(bus_id),
                voltage_pu=float(fields[2]),
                angle_rad=float(fields[3]),
                active_injection_pu=(float(fields[5]) - active_load) / base_mva,
                reactive_injection_pu=(float(fields[6]) - reactive_load) / base_mva,
            )
        )
    if not results:
        raise RuntimeError("Native report did not contain solved bus results")
    return results


def _parse_branches(report: str) -> list[BranchPowerFlowResult]:
    marker = "Branch flows and losses"
    section = report[report.find(marker) :] if marker in report else ""
    results = []
    for line in section.splitlines():
        fields = line.split()
        if len(fields) < 12 or not fields[0].isdigit():
            continue
        results.append(
            BranchPowerFlowResult(
                from_bus=int(fields[1]), to_bus=int(fields[2]), circuit=1,
                active_from_mw=float(fields[3]), reactive_from_mvar=float(fields[4]),
                active_to_mw=float(fields[5]), reactive_to_mvar=float(fields[6]),
                loading_percent=float(fields[8]), active_loss_mw=float(fields[9]),
                reactive_loss_mvar=float(fields[10]),
            )
        )
    return results


def _summary_value(report: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}:\s*(\S+)", report, re.MULTILINE)
    return match.group(1) if match else ""


def _summary_float(report: str, label: str, default: float) -> float:
    value = _summary_value(report, label)
    try:
        return float(value)
    except ValueError:
        return default


def _magnitude(value: object) -> float:
    try:
        from o_grid.units import get_magnitude

        return float(get_magnitude(value))
    except (TypeError, ValueError):
        return 0.0