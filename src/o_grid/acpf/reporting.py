"""Text reporting for in-process AC power-flow runs."""

from __future__ import annotations

from collections.abc import Callable

from o_grid.acpf.results import ACPowerFlowResult, IterationPowerFlowResult


class LiveIterationReporter:
    """Print and retain iteration rows as solver kernels produce them."""

    def __init__(self, solver: str) -> None:
        title = f"Iteration-by-iteration convergence trace ({_solver_title(solver)})"
        self.rule = "-" * max(62, len(title))
        self.header = [
            "  it       max|dP|       max|dQ|        max|R|       max|dx|",
            "----  ------------  ------------  ------------  ------------",
        ]
        self.lines = [title, self.rule, "Base solve", *self.header]

    @property
    def callback(self) -> Callable[[IterationPowerFlowResult], None]:
        return self.emit

    def start(self) -> None:
        print("\n".join(self.lines), flush=True)

    def emit(self, item: IterationPowerFlowResult) -> None:
        line = _format_iteration(item)
        self._write(line)

    def begin_phase(self, label: str) -> None:
        """Start a visibly separate solve whose iterations restart at zero."""
        self._write(self.rule)
        self._write(label)
        for line in self.header:
            self._write(line)

    def accept(self, label: str) -> None:
        self._write(f"[{label} accepted]")

    def fail(self, label: str) -> None:
        self._write(f"[{label} did not converge]")

    def reject(self, label: str) -> None:
        self._write(f"[{label} rejected; previous converged solution restored]")

    def finish(self) -> str:
        self._write(self.rule)
        return "\n".join(self.lines)

    def _write(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)


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
    rows.extend(_format_iteration(item) for item in result.iteration_trace)
    rows.append(rule)
    return "\n".join(rows)


def _solver_title(solver: str) -> str:
    return {
        "newton-raphson": "Newton-Raphson",
        "fast-decoupled": "Fast-decoupled",
        "primal-dual": "Primal-dual OPF",
    }.get(solver, solver)


def _format_iteration(item: IterationPowerFlowResult) -> str:
    return (
        f"{item.iteration:4d}  {item.max_dp:12.4e}  {item.max_dq:12.4e}  "
        f"{item.max_residual:12.4e}  {item.max_step:12.4e}"
    )
