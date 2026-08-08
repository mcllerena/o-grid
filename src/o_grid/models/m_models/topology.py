"""MATPOWER ``bus`` and ``gen`` tables to o-grid AC bus and area components."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from o_grid.models.enums import ACBusTypes
from o_grid.models.named_tuples import MinMax
from o_grid.models.topology import ACBus, Area
from o_grid.units import ActivePower, Angle, PerUnit, ReactivePower, Voltage

BUS_TYPE_BY_CODE = {
    1: ACBusTypes.PQ,
    2: ACBusTypes.PV,
    3: ACBusTypes.REF,
    4: ACBusTypes.ISOLATED,
}


def ACBuses(
    bus: Sequence[Mapping[str, Any]],
    gen: Sequence[Mapping[str, Any]] = (),
    *,
    base_mva: float = 100.0,
) -> tuple[list[ACBus], list[Area]]:
    """Build ``ACBus`` and ``Area`` components from MATPOWER bus/gen rows."""
    records = list(bus)
    generator_records = list(gen)

    area_numbers = sorted({_int(row.get("BUS_AREA", 1)) for row in records})
    areas = [Area(name=f"Area {number}", area_number=number) for number in area_numbers]
    areas_by_number = {area.area_number: area for area in areas}

    generators_by_bus: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in generator_records:
        generators_by_bus[_int(row.get("GEN_BUS"))].append(row)

    bus_components: list[ACBus] = []
    for row in records:
        number = _int(row.get("BUS_I"))
        area_number = _int(row.get("BUS_AREA", 1))
        bus_generators = generators_by_bus.get(number, [])
        component = ACBus(
            name=f"Bus {number}",
            number=number,
            bustype=BUS_TYPE_BY_CODE.get(_int(row.get("BUS_TYPE", 1)), ACBusTypes.PQ),
            area=areas_by_number[area_number],
            base_voltage=Voltage(_number(row.get("BASE_KV", 1.0)), "kV"),
            voltage_limits=MinMax(
                min=_number(row.get("VMIN", 0.9)),
                max=_number(row.get("VMAX", 1.1)),
            ),
            initial_voltage=PerUnit(_number(row.get("VM", 1.0)), "pu"),
            angle=Angle(_number(row.get("VA", 0.0)), "degree"),
            active_generation=ActivePower(
                sum(_number(generator.get("PG", 0.0)) for generator in bus_generators),
                "MW",
            ),
            reactive_generation=ReactivePower(
                sum(_number(generator.get("QG", 0.0)) for generator in bus_generators),
                "MVAr",
            ),
            active_load=ActivePower(_number(row.get("PD", 0.0)), "MW"),
            reactive_load=ReactivePower(_number(row.get("QD", 0.0)), "MVAr"),
            capacitor_reactor=ReactivePower(_number(row.get("GS", 0.0)) * base_mva, "MVAr"),
            min_reactive_generation=_reactive_limits(generator_records, number, "QMIN"),
            max_reactive_generation=_reactive_limits(generator_records, number, "QMAX"),
        )
        component.ext["pwf_values"] = {"name": str(number), "area": area_number}
        bus_components.append(component)
    return bus_components, areas


def _reactive_limits(
    records: Sequence[Mapping[str, Any]],
    bus_number: int,
    field: str,
) -> ReactivePower | None:
    values = [
        _number(row[field])
        for row in records
        if _int(row.get("GEN_BUS")) == bus_number and row.get(field) is not None
    ]
    if not values:
        return None
    return ReactivePower(sum(values), "MVAr")


def _int(value: Any) -> int:
    return int(float(value))


def _number(value: Any) -> float:
    return float(value)
