"""Parse a PWF case and solve it directly as an infrasys system."""

from __future__ import annotations

from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser, ExportSolution  # noqa: F401
from o_grid.acpf import NewtonRaphsonPowerFlow, OptimizationACPowerFlow  # noqa: F401
from o_grid.models.topology import ACBus  # noqa: F401
from o_grid.system import AnaredeSystem  # noqa: F401

# Parse PWF case and load infrasys system
sys_name = "CASO01-FLOW"
DATA_PATH = Path(f"tests/data/pwf/br-data-2026-1q/{sys_name}.PWF")

parse_config = AnaredeConfig(
    system_name=sys_name,
    pwf_path=str(DATA_PATH),
)
parse_context = PluginContext(
    config=parse_config,
    store=DataStore(path=DATA_PATH.parent),
)
parsed_system = AnaredeParser.from_context(parse_context).run().system

# total_load = 0.0
# for bus in parsed_system.get_components(ACBus):
#     total_load += bus.active_load.magnitude

# MW Load = 85231.91700000002 -> CASO_FINAL_EQV2020
# MW Load = 107532.08 -> LEN_A_4_2020_SECO_2023VM_SE_EXP_N
# MW Load = 84088.955 -> 20240820_C_00-00
# MW Load = 84088.955 -> 20240820_C_18-30

# Run power flow on infrasys system
nr_pf = NewtonRaphsonPowerFlow(
    system=parsed_system,
    max_iterations=30,
    max_control_passes=12,
    print_iterations=True,
)
# assert isinstance(nr_pf, AnaredeSystem)
# assert nr_pf.power_flow_results is not None

# opt_pf = OptimizationACPowerFlow(
#     system=parsed_system,
#     objective_function="squared_generation",
#     max_iterations=100,
#     print_iterations=True,
# )
# assert isinstance(opt_pf, AnaredeSystem)

# Export results to xlsx
export_sys = ExportSolution(
    system=nr_pf,
    format="excel",
    output_path=Path(f"tests/data/pwf/{sys_name}_solution.xlsx"),
)

# Where to locate BESS, to help converge the system (with ACOPF)
# Optimal location of BESS (having the ACPF already)
# Electrolizer (dynamic loads that work on P and Q) -> Add constraints (Vlim, Ilim..)


# NLR (ParaEMT Simulation to integrate) -> Input to Dynamic Simulation

# How to improve voltage profiles/frequency stability (Need of Dyn. Sim.)
