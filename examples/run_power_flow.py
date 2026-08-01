"""Parse a PWF case and solve it directly as an infrasys system."""

from __future__ import annotations

from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser, ExportSolution
from o_grid.acpf import NewtonRaphsonPowerFlow
from o_grid.system import AnaredeSystem

# Parse PWF case and load infrasys system
sys_name = "NEXPSE19M_19"
DATA_PATH = Path(f"tests/data/pwf/{sys_name}.pwf")

parse_config = AnaredeConfig(
    system_name=sys_name,
    pwf_path=str(DATA_PATH),
)
parse_context = PluginContext(
    config=parse_config,
    store=DataStore(path=DATA_PATH.parent),
)
parsed_system = AnaredeParser.from_context(parse_context).run().system

# Run power flow on infrasys system
nr_pf = NewtonRaphsonPowerFlow(
    system=parsed_system,
    max_iterations=30,
    print_iterations=True,
)
assert isinstance(nr_pf, AnaredeSystem)
assert nr_pf.power_flow_results is not None

# Export results to xlsx
export_sys = ExportSolution(
    system=nr_pf,
    format="excel",
    output_path=Path(f"tests/data/pwf/{sys_name}_solution.xlsx"),
)
