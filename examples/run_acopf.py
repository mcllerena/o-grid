"""Run ACOPF on the Brazilian equivalent and full-system cases."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser, ExportSolution
from o_grid.acopf import ACOptimalPowerFlow, implemented_formulations
from o_grid.acopf.optimization import LINEAR_FORMULATIONS

data_dir = Path("tests/data/pwf")
# Conic formulations bootstrap Clarabel.jl from the package-shipped Julia project.
formulations = implemented_formulations()
case_names = (
    # "CASO_FINAL_EQV2020",
    "LEN_A_4_2020_SECO_2023VM_SE_EXP_N",
    # "LENA_BD0320R0_2Q2020_R1_CASO_12",
)

summary_rows = []
for sys_name in case_names:
    data_path = data_dir / f"{sys_name}.PWF"
    for formulation in formulations:
        formulation_parse_config = AnaredeConfig(
            system_name=sys_name,
            pwf_path=str(data_path),
            log=False,
        )
        formulation_parse_context = PluginContext(
            config=formulation_parse_config,
            store=DataStore(path=data_path.parent),
        )
        formulation_system = AnaredeParser.from_context(formulation_parse_context).run().system
        started = time.perf_counter()
        row = {
            "case": sys_name,
            "formulation": formulation,
            "status": "failed",
            "converged": False,
            "diverged": False,
            "ac_security": None,
            "iterations": None,
            "max_mismatch_pu": None,
            "elapsed_seconds": None,
            "error": None,
        }
        try:
            run = ACOptimalPowerFlow(
                formulation=formulation,
                objective_function="voltage_deviation",
                tolerance=1.0e-3,
                # max_iterations=1000,
                # max_cpu_time=900.0,
                # print_iterations=True,
                max_iterations=500,
            ).run(formulation_system)
            information = run.system.power_flow_results.information
            solved = information.converged
            if (
                formulation in LINEAR_FORMULATIONS
                and not solved
                and not information.diverged
                and information.max_mismatch_pu is not None
                and information.max_mismatch_pu <= 1.0e-3
            ):
                status = "linearized_solved_ac_infeasible"
            else:
                status = "converged" if solved else "not_converged"
            row.update(
                status=status,
                converged=solved,
                diverged=information.diverged,
                ac_security=solved if formulation in LINEAR_FORMULATIONS else None,
                iterations=information.iterations,
                max_mismatch_pu=information.max_mismatch_pu,
            )
            ExportSolution(
                system=run.system,
                format="excel",
                output_path=data_path.with_name(f"{sys_name}_solution_{formulation}.xlsx"),
                export=False,
            )
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
            if "dense SDP formulation supports at most" in str(error):
                row["status"] = "unsupported_at_scale"
        finally:
            row["elapsed_seconds"] = time.perf_counter() - started
            summary_rows.append(row)

results = pd.DataFrame(summary_rows)
print("\nACOPF formulation comparison")
print(results.to_string(index=False))
