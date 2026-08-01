"""Parse a PWF case and solve it directly as an infrasys system."""

from __future__ import annotations

from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser
from o_grid.acpf import NewtonRaphsonPowerFlow
from o_grid.system import AnaredeSystem

DATA_PATH = Path("tests/data/pwf/CASO_FINAL_EQV2020.pwf")

parse_config = AnaredeConfig(
    system_name="CASO_FINAL_EQV2020",
    pwf_path=str(DATA_PATH),
)
parse_context = PluginContext(
    config=parse_config,
    store=DataStore(path=DATA_PATH.parent),
)
parsed_system = AnaredeParser.from_context(parse_context).run().system

nr_pf = NewtonRaphsonPowerFlow(
    system=parsed_system,
    print_iterations=True,
)
assert isinstance(nr_pf, AnaredeSystem)
assert nr_pf.power_flow_results is not None
