from pathlib import Path

import pyomo.environ as pyo

from o_grid.acpf.models import build_power_flow_case
from o_grid.acopf.optimization import build_optimization_model
from o_grid.statics.ntw_parser import NtwFileParser
from o_grid.statics.pwf_parser import ParsedAnaredeSystem


def test_data_center_binary_variables_are_linked_to_9bus_acopf() -> None:
    network = Path(__file__).parent / "data" / "ntw" / "9bus.ntw"
    parsed = ParsedAnaredeSystem.from_system(NtwFileParser(network).system)
    case = build_power_flow_case(parsed)

    model = build_optimization_model(
        case,
        active_tolerance_pu=1.0e-3,
        reactive_tolerance_pu=1.0e-3,
        control_tolerance_pu=1.0e-3,
        data_center_load_mw=1000.0,
        data_center_reactive_mvar=203.0,
        data_center_candidate_buses=(4, 5, 6, 7, 8, 9),
        data_center_sites=1,
    )

    assert len(model.data_center_site) == 6
    assert all(model.data_center_site[bus].domain is pyo.Binary for bus in model.DATA_CENTER_CANDIDATE)
    assert model.data_center_site_count.lower == model.data_center_sites
    assert model.data_center_site_count.upper == model.data_center_sites
    assert pyo.value(model.data_center_load_mw) == 1000.0