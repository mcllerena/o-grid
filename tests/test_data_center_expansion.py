import pyomo.environ as pyo

from o_grid.acpf.models.case import BusData, PowerFlowCase
from o_grid.data_center import (
    CapacityExpansionStudy,
    TransmissionExpansionProject,
    apply_transmission_expansion,
    build_capacity_expansion_model,
)
from o_grid.models import ACBusTypes


def test_capacity_expansion_has_reeds_style_accounting() -> None:
    study = CapacityExpansionStudy(
        candidate_buses=(4, 5, 6),
        cumulative_load_mw_by_year={2030: 100.0, 2035: 250.0},
        generation_mw_per_load_mw=1.2,
        generation_mvar_per_load_mw=0.2,
        capacity_factor=0.9,
        max_sites=2,
        interconnection_capacity_mw_by_bus={4: 50.0, 5: 50.0, 6: 50.0},
        interconnection_expansion_cost_by_bus={4: 1.0, 5: 1.0, 6: 1.0},
        transmission_projects=(
            TransmissionExpansionProject(
                name="line-4-5",
                connection_bus=4,
                from_bus=4,
                to_bus=5,
                resistance=0.01,
                reactance=0.1,
                charging=0.0,
                rating_mva=300.0,
                capacity_mw=250.0,
                investment_cost=10.0,
                available_year=2035,
            ),
        ),
    )

    model = build_capacity_expansion_model(study)

    assert set(model.YEAR) == {2030, 2035}
    assert set(model.BUS) == {4, 5, 6}
    assert model.INV_LOADSITE.index_set().dimen == 2
    assert model.CAP_LOADSITE.index_set().dimen == 2
    assert model.generation_link[4, 2030].body.polynomial_degree() == 1
    assert model.siting_target[2035].lower == 250.0
    assert model.site_count.upper == 2.0
    assert model.reactive_generation_link[4, 2030].body.polynomial_degree() == 1
    assert model.interconnection_capacity_accounting[4, 2035].body.polynomial_degree() == 1
    assert model.interconnection_limit[4, 2035].body.polynomial_degree() == 1
    assert set(model.PROJECT) == {"line-4-5"}
    assert model.BUILD_TRANSMISSION["line-4-5", 2030].is_binary()
    assert pyo.value(model.SITE_ACTIVE[4]) == 0.0


def test_apply_transmission_expansion_appends_fixed_branch_without_mutation() -> None:
    case = PowerFlowCase(
        base_mva=100.0,
        buses=[
            BusData(
                4, "4", ACBusTypes.REF, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 1.1, 230.0, "A"
            ),
            BusData(
                5, "5", ACBusTypes.PQ, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 1.1, 230.0, "A"
            ),
        ],
        branches=[],
    )
    project = TransmissionExpansionProject(
        "line-4-5", 4, 4, 5, 0.01, 0.1, 0.0, 300.0, 250.0, 10.0
    )

    upgraded = apply_transmission_expansion(case, [project])

    assert len(case.branches) == 0
    assert len(upgraded.branches) == 1
    assert upgraded.branches[0].rating == 300.0