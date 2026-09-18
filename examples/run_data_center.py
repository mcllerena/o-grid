"""Run ReEDS-style data-center capacity expansion and ACOPF evaluation."""

from __future__ import annotations

from pathlib import Path

from o_grid.acpf import ACOptimalPowerFlow
from o_grid.acpf.models.case import build_power_flow_case
from o_grid.data_center import (
    CapacityExpansionStudy,
    DataCenterLoad,
    LoadPlacement,
    TransmissionExpansionProject,
    apply_load,
    apply_transmission_expansion,
    projects_built_by_year,
    solve_capacity_expansion,
)
from o_grid.parser import AnaredeInfrasysParser


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    network_path = project_root / "tests" / "data" / "pwf" / "LEN_A_4_2020_SECO_2023VM_SE_EXP_N.pwf"
    target_year = 2035
    candidate_buses = (10,)

    parsed_system = AnaredeInfrasysParser().parse(network_path)
    expansion = CapacityExpansionStudy(
        candidate_buses=candidate_buses,
        cumulative_load_mw_by_year={2030: 500.0, 2035: 1000.0},
        generation_mw_per_load_mw=0.0,
        generation_mvar_per_load_mw=0.0,
        max_sites=1,
        interconnection_capacity_mw_by_bus={10: 300.0},
        interconnection_expansion_cost_by_bus={10: 0.05},
        max_interconnection_expansion_mw_by_bus={10: 0.0},
        transmission_projects=(
            TransmissionExpansionProject(
                name="data-center-grid-reinforcement",
                connection_bus=10,
                from_bus=10,
                to_bus=11,
                resistance=0.002,
                reactance=0.08,
                charging=0.02,
                rating_mva=1200.0,
                capacity_mw=700.0,
                investment_cost=20.0,
                available_year=2030,
            ),
        ),
        load_site_cost_by_bus={bus: 1.0 for bus in candidate_buses},
        generation_cost_by_bus={bus: 1.0 for bus in candidate_buses},
    )
    plan = solve_capacity_expansion(expansion)
    selected_bus = next(bus for bus, active in plan.site_active.items() if active > 0.5)
    load_mw = plan.load_capacity_mw[selected_bus, target_year]
    generation_mw = plan.generation_capacity_mw[selected_bus, target_year]
    generation_mvar = plan.reactive_generation_capacity_mvar[selected_bus, target_year]
    interconnection_mw = plan.interconnection_capacity_mw[selected_bus, target_year]
    built_projects = projects_built_by_year(
        expansion.transmission_projects, plan.transmission_built, target_year
    )
    upgraded_case = apply_transmission_expansion(
        build_power_flow_case(parsed_system), built_projects
    )

    print(f"Capacity-expansion target year: {target_year}")
    print(f"Selected bus: {selected_bus}")
    print(f"Sited load: {load_mw:.1f} MW")
    print(f"Co-located generation: {generation_mw:.1f} MW")
    print(f"Reactive generation capability: {generation_mvar:.1f} MVAr")
    print(f"Interconnection capacity: {interconnection_mw:.1f} MW")
    print(f"Built transmission projects: {len(built_projects)}")
    print(f"AC validation branches: {len(upgraded_case.branches)}")

    validation_case = apply_load(
        upgraded_case,
        LoadPlacement(
            selected_buses=(selected_bus,),
            load=DataCenterLoad(active_mw=load_mw, power_factor=0.98),
        ),
    )
    study = ACOptimalPowerFlow(max_iterations=500)
    result = study.run(parsed_system, case_override=validation_case)

    print(result.stdout)
    print(f"Converged: {result.result.converged}")
    print(f"Maximum mismatch: {result.result.max_mismatch:.6e} pu")


if __name__ == "__main__":
    main()
