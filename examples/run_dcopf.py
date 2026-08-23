"""Run the HiGHS-backed DC optimal power-flow algorithm."""

from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser, DCOptimalPowerFlow, ExportSolution

sys_name = "CASO_FINAL_EQV2020"
data_path = Path(f"tests/data/pwf/{sys_name}.PWF")

config = AnaredeConfig(system_name=sys_name, pwf_path=str(data_path))
context = PluginContext(config=config, store=DataStore(path=data_path.parent))

system = AnaredeParser.from_context(context).run().system

run = DCOptimalPowerFlow(
    param_opt="cold_start",
    enforce_branch_limits=False,
).run(system)

print(f"DCOPF converged: {run.result.converged}")
print(f"DCOPF iterations: {run.result.iterations}")

export_sys = ExportSolution(
    system=run.system,
    format="excel",
    output_path=data_path.with_name(f"{sys_name}_solution_dcopf.xlsx"),
)
