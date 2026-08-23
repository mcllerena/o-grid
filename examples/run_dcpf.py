"""Run the DC power-flow algorithm on a power-flow case."""

from __future__ import annotations

from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser, DCPowerFlow, ExportSolution

sys_name = "CASO_FINAL_EQV2020"
data_path = Path(f"tests/data/pwf/{sys_name}.PWF")

parse_config = AnaredeConfig(
    system_name=sys_name,
    pwf_path=str(data_path),
)
parse_context = PluginContext(
    config=parse_config,
    store=DataStore(path=data_path.parent),
)
parsed_system = AnaredeParser.from_context(parse_context).run().system

dcpf_run = DCPowerFlow(lossy_flows=True).run(parsed_system)
dcpf = dcpf_run.system
print(f"DCPF iterations: {dcpf_run.result.iterations}")

dcpf_export = ExportSolution(
    system=dcpf,
    format="excel",
    output_path=data_path.with_name(f"{sys_name}_solution_dcpf.xlsx"),
)
