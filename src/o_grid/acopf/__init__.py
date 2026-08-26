"""AC optimal power-flow algorithms."""

from typing import Any

from o_grid.acopf.formulations import (
    FORMULATION_REGISTRY,
    implemented_formulations,
    resolve_formulation,
)


def __getattr__(name: str) -> Any:
    if name in {
        "ACOptimalPowerFlow",
        "build_optimization_model",
        "solution_metrics",
        "solve_optimization_model",
        "summarize_solution",
    }:
        from o_grid.acopf import optimization

        return getattr(optimization, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ACOptimalPowerFlow",
    "FORMULATION_REGISTRY",
    "build_optimization_model",
    "solution_metrics",
    "solve_optimization_model",
    "summarize_solution",
    "implemented_formulations",
    "resolve_formulation",
]
