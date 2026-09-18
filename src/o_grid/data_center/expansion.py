"""ReEDS-style multi-period capacity expansion for large-load siting."""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo

from o_grid.data_center.models import CapacityExpansionPlan, CapacityExpansionStudy


def _component(model: Any, name: str) -> Any:
    return getattr(model, name)


def build_capacity_expansion_model(study: CapacityExpansionStudy) -> pyo.ConcreteModel:
    """Build load-site investment, cumulative capacity, and generation co-expansion."""
    years = tuple(sorted(study.cumulative_load_mw_by_year))
    buses = study.candidate_buses
    model: Any = pyo.ConcreteModel("data_center_capacity_expansion")
    model.YEAR = pyo.Set(initialize=years, ordered=True)
    model.BUS = pyo.Set(initialize=buses, ordered=True)
    projects = {project.name: project for project in study.transmission_projects}
    model.PROJECT = pyo.Set(initialize=tuple(projects), ordered=True)
    model.INV_LOADSITE = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.CAP_LOADSITE = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.INV_GENERATION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.CAP_GENERATION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.INV_REACTIVE_GENERATION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.CAP_REACTIVE_GENERATION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.INV_INTERCONNECTION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.CAP_INTERCONNECTION = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.OP_LOADSITE = pyo.Var(model.BUS, model.YEAR, domain=pyo.NonNegativeReals)
    model.SITE_ACTIVE = pyo.Var(model.BUS, domain=pyo.Binary, initialize=0)
    model.BUILD_TRANSMISSION = pyo.Var(model.PROJECT, model.YEAR, domain=pyo.Binary)

    def capacity_rule(m: Any, bus: int, year: int):
        previous = [prior for prior in years if prior <= year]
        return _component(m, "CAP_LOADSITE")[bus, year] == sum(
            _component(m, "INV_LOADSITE")[bus, prior] for prior in previous
        )

    model.load_capacity_accounting = pyo.Constraint(model.BUS, model.YEAR, rule=capacity_rule)
    model.generation_capacity_accounting = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "CAP_GENERATION")[bus, year]
        == sum(
            _component(m, "INV_GENERATION")[bus, prior]
            for prior in years
            if prior <= year
        ),
    )
    model.generation_link = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "INV_GENERATION")[bus, year]
        == study.generation_mw_per_load_mw * _component(m, "INV_LOADSITE")[bus, year],
    )
    model.transmission_build_once = pyo.Constraint(
        model.PROJECT,
        rule=lambda m, project: sum(
            _component(m, "BUILD_TRANSMISSION")[project, year] for year in years
        )
        <= 1,
    )
    model.reactive_generation_capacity_accounting = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "CAP_REACTIVE_GENERATION")[bus, year]
        == sum(
            _component(m, "INV_REACTIVE_GENERATION")[bus, prior]
            for prior in years
            if prior <= year
        ),
    )
    model.reactive_generation_link = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "INV_REACTIVE_GENERATION")[bus, year]
        == study.generation_mvar_per_load_mw * _component(m, "INV_LOADSITE")[bus, year],
    )
    model.interconnection_capacity_accounting = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "CAP_INTERCONNECTION")[bus, year]
        == study.interconnection_capacity_mw_by_bus.get(
            bus, max(study.cumulative_load_mw_by_year.values())
        )
        + sum(
            _component(m, "INV_INTERCONNECTION")[bus, prior]
            for prior in years
            if prior <= year
        )
        + sum(
            projects[project].capacity_mw * m.BUILD_TRANSMISSION[project, prior]
            for project in projects
            if projects[project].connection_bus == bus
            for prior in years
            if prior <= year
        ),
    )
    model.transmission_availability = pyo.Constraint(
        model.PROJECT,
        model.YEAR,
        rule=lambda m, project, year: _component(m, "BUILD_TRANSMISSION")[project, year]
        == 0
        if projects[project].available_year and year < projects[project].available_year
        else pyo.Constraint.Skip,
    )
    model.interconnection_limit = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: m.CAP_LOADSITE[bus, year]
        <= m.CAP_INTERCONNECTION[bus, year],
    )
    if study.max_interconnection_expansion_mw_by_bus is not None:
        max_interconnection_expansion = study.max_interconnection_expansion_mw_by_bus
        model.interconnection_expansion_limit = pyo.Constraint(
            model.BUS,
            model.YEAR,
            rule=lambda m, bus, year: sum(
                _component(m, "INV_INTERCONNECTION")[bus, prior]
                for prior in years
                if prior <= year
            )
            <= max_interconnection_expansion.get(bus, 0.0),
        )
    model.siting_target = pyo.Constraint(
        model.YEAR,
        rule=lambda m, year: sum(
            _component(m, "CAP_LOADSITE")[bus, year] for bus in buses
        )
        == study.cumulative_load_mw_by_year[year],
    )
    model.site_activation = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "CAP_LOADSITE")[bus, year]
        <= (study.max_capacity_mw_by_bus or {}).get(
            bus, max(study.cumulative_load_mw_by_year.values())
        )
        * _component(m, "SITE_ACTIVE")[bus],
    )
    if study.max_sites is not None:
        model.site_count = pyo.Constraint(
            expr=sum(_component(model, "SITE_ACTIVE")[bus] for bus in buses)
            <= study.max_sites
        )
    model.utilization = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "OP_LOADSITE")[bus, year]
        >= study.capacity_factor * _component(m, "CAP_LOADSITE")[bus, year],
    )
    model.operational_capacity = pyo.Constraint(
        model.BUS,
        model.YEAR,
        rule=lambda m, bus, year: _component(m, "OP_LOADSITE")[bus, year]
        <= _component(m, "CAP_LOADSITE")[bus, year],
    )
    model.objective = pyo.Objective(
        expr=sum(
            (study.load_site_cost_by_bus.get(bus, 0.0) * _component(model, "INV_LOADSITE")[bus, year])
            + (study.generation_cost_by_bus.get(bus, 0.0) * _component(model, "INV_GENERATION")[bus, year])
            + (
                study.interconnection_expansion_cost_by_bus.get(bus, 0.0)
                * _component(model, "INV_INTERCONNECTION")[bus, year]
            )
            + sum(
                projects[project].investment_cost
                * _component(model, "BUILD_TRANSMISSION")[project, year]
                for project in model.PROJECT
            )
            for bus in buses
            for year in years
        ),
        sense=pyo.minimize,
    )
    return model


def solve_capacity_expansion(
    study: CapacityExpansionStudy,
    *,
    solver_name: str = "appsi_highs",
) -> CapacityExpansionPlan:
    """Solve a capacity-expansion study and return cumulative capacities."""
    model = build_capacity_expansion_model(study)
    solver = pyo.SolverFactory(solver_name)
    if solver is None or not solver.available(False):
        raise RuntimeError(f"capacity-expansion solver is unavailable: {solver_name}")
    results = solver.solve(model)
    termination = getattr(results.solver, "termination_condition", None)
    if termination != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"capacity-expansion solve failed: {termination}")
    return CapacityExpansionPlan(
        load_capacity_mw={
            (bus, year): float(pyo.value(_component(model, "CAP_LOADSITE")[bus, year]))
            for bus in study.candidate_buses
            for year in study.cumulative_load_mw_by_year
        },
        transmission_built={
            (project.name, year): float(
                pyo.value(_component(model, "BUILD_TRANSMISSION")[project.name, year])
            )
            for project in study.transmission_projects
            for year in study.cumulative_load_mw_by_year
        },
        generation_capacity_mw={
            (bus, year): float(pyo.value(_component(model, "CAP_GENERATION")[bus, year]))
            for bus in study.candidate_buses
            for year in study.cumulative_load_mw_by_year
        },
        reactive_generation_capacity_mvar={
            (bus, year): float(
                pyo.value(_component(model, "CAP_REACTIVE_GENERATION")[bus, year])
            )
            for bus in study.candidate_buses
            for year in study.cumulative_load_mw_by_year
        },
        site_active={
            bus: float(pyo.value(_component(model, "SITE_ACTIVE")[bus]))
            for bus in study.candidate_buses
        },
        interconnection_capacity_mw={
            (bus, year): float(
                pyo.value(_component(model, "CAP_INTERCONNECTION")[bus, year])
            )
            for bus in study.candidate_buses
            for year in study.cumulative_load_mw_by_year
        },
    )