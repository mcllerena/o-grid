"""Text reporting for in-process AC power-flow runs."""

from __future__ import annotations

from o_grid.acpf.results import ACPowerFlowResult


def format_power_flow_report(
    result: ACPowerFlowResult,
    *,
    print_iterations: bool,
) -> str:
    """Format the optional iteration trace."""
    return _format_iteration_trace(result) if print_iterations else ""


def _format_iteration_trace(result: ACPowerFlowResult) -> str:
    title = f"Iteration-by-iteration convergence trace ({_solver_title(result.solver)})"
    rule = "-" * max(62, len(title))
    rows = [
        title,
        rule,
        "  it       max|dP|       max|dQ|        max|R|       max|dx|",
        "----  ------------  ------------  ------------  ------------",
    ]
    rows.extend(
        f"{item.iteration:4d}  {item.max_dp:12.4e}  {item.max_dq:12.4e}  "
        f"{item.max_residual:12.4e}  {item.max_step:12.4e}"
        for item in result.iteration_trace
    )
    rows.append(rule)
    return "\n".join(rows)


def _solver_title(solver: str) -> str:
    return {
        "newton-raphson": "Newton-Raphson",
        "fast-decoupled": "Fast-decoupled",
    }.get(solver, solver)
