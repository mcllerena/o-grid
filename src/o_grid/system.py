"""infrasys ``System`` subclass with an ANAREDE-aware summary."""

from __future__ import annotations

from infrasys.system import System, SystemInfo
from rich import print as _pprint
from rich.table import Table

# Component types reported under "Power Flow Information" instead of "Component Information".
POWER_FLOW_COMPONENT_TYPES: tuple[str, ...] = ("PowerFlowOption", "ProgramConstant")


class AnaredeSystemInfo(SystemInfo):
    """System summary that lists power-flow option/constant rows in their own table."""

    def extract_system_counts(self) -> tuple[int, int, dict, dict]:
        component_count, ts_count, type_count, ts_type_count = super().extract_system_counts()
        filtered = {
            name: count
            for name, count in type_count.items()
            if name not in POWER_FLOW_COMPONENT_TYPES
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


class AnaredeSystem(System):
    """infrasys ``System`` that renders a dedicated Power Flow Information summary."""

    def info(self) -> None:
        AnaredeSystemInfo(system=self).render()
