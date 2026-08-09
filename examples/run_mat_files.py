"""Solve a MATPOWER case file through the o-grid plugin pipeline.

Usage:
    python examples/run_mat_files.py [case.m]
"""

from __future__ import annotations

from pathlib import Path

from r2x_core.plugin_context import PluginContext
from r2x_core.store import DataStore

from o_grid.acpf import NewtonRaphsonPowerFlow, OptimizationACPowerFlow  # noqa: F401
from o_grid.exporter import ExportSolution
from o_grid.plugin_config import MatpowerConfig
from o_grid.plugin_parser import MatPowerParser

DATA_PATH = Path(__file__).resolve().parents[1] / "tests" / "data" / "mat"

sys_name = "case_SyntheticUSA"
pwf_path = DATA_PATH / f"{sys_name}.m"
if not pwf_path.exists():
    raise FileNotFoundError(f"MATPOWER case file not found: {pwf_path}")

config = MatpowerConfig(system_name=sys_name, pwf_path=str(pwf_path))
store = DataStore(path=DATA_PATH.parent)
parse_context = PluginContext(config=config, store=store)
parsed = MatPowerParser.from_context(parse_context).run()

# opt_pf = OptimizationACPowerFlow(
#     system=parsed.system,
#     objective_function="squared_generation",
#     max_iterations=100,
#     print_iterations=True,
# )
opt_pf = NewtonRaphsonPowerFlow(
    system=parsed.system,
    max_iterations=100,
    max_control_passes=0,
    print_iterations=True,
)
output_path = DATA_PATH.parent / "mat" / f"{sys_name}_solution.xlsx"
ExportSolution(system=opt_pf, format="excel", output_path=output_path)
# print(f"Solution exported to {output_path}")
