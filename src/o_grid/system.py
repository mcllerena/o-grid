"""infrasys ``System`` subclass with an ANAREDE-aware summary."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from infrasys.system import System, SystemInfo
from rich import print as _pprint
from rich.table import Table

if TYPE_CHECKING:
    from infrasys import Component

    from o_grid.acpf.models.results import PowerFlowResults

# Component types reported under "Power Flow Information" instead of "Component Information".
POWER_FLOW_COMPONENT_TYPES: tuple[str, ...] = ("PowerFlowOption", "ProgramConstant")
RESULT_COMPONENT_TYPES: tuple[str, ...] = (
    "StatisticResultsInformation",
    "ACBusResults",
    "ACLineResults",
    "LTCTransformerResults",
    "PhaseShiftingTransformerResults",
    "SwitchDeviceResults",
    "StaticVARCompensatorResults",
    "ControllableSeriesCompensatorResults",
    "DCLineResults",
)


class AnaredeSystemInfo(SystemInfo):
    """System summary that lists power-flow option/constant rows in their own table."""

    def extract_system_counts(self) -> tuple[int, int, dict, dict]:
        component_count, ts_count, type_count, ts_type_count = super().extract_system_counts()
        component_count -= sum(type_count.get(name, 0) for name in RESULT_COMPONENT_TYPES)
        filtered = {
            name: count
            for name, count in type_count.items()
            if name not in (*POWER_FLOW_COMPONENT_TYPES, *RESULT_COMPONENT_TYPES)
        }
        return component_count, ts_count, filtered, ts_type_count

    def render(self) -> None:
        # Renders System, Component Information (power-flow types filtered out), and time series.
        super().render()

        type_count = super().extract_system_counts()[2]
        power_flow_table = Table(
            title="Power Flow Information",
            show_header=True,
            title_justify="left",
            title_style="bold",
        )
        power_flow_table.add_column("Type", min_width=20)
        power_flow_table.add_column("Count", justify="right")
        for component_type in POWER_FLOW_COMPONENT_TYPES:
            count = type_count.get(component_type)
            if count:
                power_flow_table.add_row(component_type, f"{count}")

        if power_flow_table.rows:
            _pprint(power_flow_table)

        system = self.system
        results = getattr(system, "power_flow_results", None)
        if results is not None:
            results_table = Table(
                title="Results Information",
                show_header=True,
                title_justify="left",
                title_style="bold",
            )
            results_table.add_column("Type", min_width=36)
            results_table.add_column("Count", justify="right")
            type_count = SystemInfo.extract_system_counts(self)[2]
            for component_type in RESULT_COMPONENT_TYPES[1:]:
                results_table.add_row(component_type, str(type_count.get(component_type, 0)))
            _pprint(results_table)

            information = results.information
            statistics_table = Table(
                title="Statistic Results Information",
                show_header=True,
                title_justify="left",
                title_style="bold",
            )
            statistics_table.add_column("Property", min_width=38)
            statistics_table.add_column("Value", justify="right")
            statistics_table.add_row("Case", information.source_path)
            statistics_table.add_row("Base MVA", f"{information.base_mva:g}")
            statistics_table.add_row(
                "Estimated dense matrix memory",
                f"{information.estimated_dense_matrix_memory_gb:.2f} GB",
            )
            statistics_table.add_row("Solver mode", information.solver_mode)
            statistics_table.add_row(
                "AC convergence criterion",
                f"max residual <= {information.convergence_tolerance_pu:.4e} pu",
            )
            statistics_table.add_row(
                "AC divergence voltage window",
                f"[{information.divergence_voltage_minimum_pu:.4e}, "
                f"{information.divergence_voltage_maximum_pu:.4e}] pu",
            )
            statistics_table.add_row(
                "Near-zero guard tolerance",
                f"{information.near_zero_guard_tolerance:.4e}",
            )
            statistics_table.add_section()
            statistics_table.add_row("Converged", "yes" if information.converged else "no")
            statistics_table.add_row("Iterations", str(information.iterations))
            mismatch = information.max_mismatch_pu
            statistics_table.add_row(
                "Max mismatch", f"{mismatch:.4e} pu" if mismatch is not None else "n/a"
            )
            statistics_table.add_row(
                "Scheduled generation", f"{information.scheduled_generation_mw:.3f} MW"
            )
            statistics_table.add_row(
                "Solved generation", f"{information.solved_generation_mw:.3f} MW"
            )
            statistics_table.add_row("Total load", f"{information.total_load_mw:.3f} MW")
            statistics_table.add_row(
                "Branch active losses", f"{information.branch_active_losses_mw:.3f} MW"
            )
            statistics_table.add_row(
                "Generation - load - branch losses",
                f"{information.power_balance_mw:.3f} MW",
            )
            statistics_table.add_row(
                "Voltage upper violations", str(information.voltage_upper_violations)
            )
            statistics_table.add_row(
                "Voltage lower violations", str(information.voltage_lower_violations)
            )
            statistics_table.add_row("Line flow overloads", str(information.line_flow_overloads))
            _pprint(statistics_table)


class AnaredeSystem(System):
    """infrasys ``System`` that renders a dedicated Power Flow Information summary."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._anarede_source: Path | None = None
        self._components_by_block: dict[str, list[Component]] = {}
        self._component_classes: dict[str, type[Component]] = {}
        self._power_flow_results: PowerFlowResults | None = None

    def attach_parse_context(
        self,
        source: Path,
        components_by_block: dict[str, list[Component]],
        component_classes: dict[str, type[Component]],
    ) -> None:
        """Retain the parsed records required by in-process numerical models."""
        self._anarede_source = source
        self._components_by_block = components_by_block
        self._component_classes = component_classes

    @property
    def power_flow_results(self) -> PowerFlowResults | None:
        """Return typed results from the latest AC power-flow run."""
        return self._power_flow_results

    def set_power_flow_results(self, results: PowerFlowResults) -> None:
        """Replace and attach typed AC power-flow result components."""
        if self._power_flow_results is not None:
            for component in self._power_flow_results.components():
                self.remove_component(component, force=True)
        self._power_flow_results = results
        for component in results.components():
            self.add_component(component)

    def info(self) -> None:
        AnaredeSystemInfo(system=self).render()
