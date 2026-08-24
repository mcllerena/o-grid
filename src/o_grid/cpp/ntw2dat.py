"""Convert ANAREDE NTW files to native C++ DAT files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from o_grid.cpp.dat_writer import write_dat
from o_grid.statics.ntw_parser import NtwFileParser
from o_grid.units import get_magnitude


_DEFAULT_CONFIG = {
    "field_order": {
        "DBAR": ["number", "name", "type", "area", "voltage", "angle", "active_generation", "reactive_generation", "active_load", "reactive_load", "shunt_susceptance", "maximum_voltage", "minimum_voltage"],
        "DLIN": ["from_bus", "to_bus", "circuit", "resistance", "reactance", "charging", "rating", "tap", "phase_shift"],
        "DGER": ["bus", "identifier", "active_generation", "reactive_generation", "maximum_reactive_generation", "minimum_reactive_generation", "voltage", "controlled_bus", "status"],
        "DCAI": ["bus", "identifier", "status", "active_power", "reactive_power"],
        "DLIN_TRANSFORMER": ["from_bus", "to_bus", "circuit", "resistance", "reactance", "tap", "rating"],
        "DSHUNT": ["bus", "control_mode", "maximum_voltage", "minimum_voltage", "controlled_bus", "reactive_power", "status"],
        "DCTE": ["mnemonic", "value"],
    },
    "name_aliases": {
        "number": "No", "name": "Name", "type": "Tb", "area": "Are", "voltage": "V", "angle": "A0",
        "active_generation": "Pg", "reactive_generation": "Qg", "maximum_reactive_generation": "Qgm",
        "minimum_reactive_generation": "Qgn", "active_load": "Pl", "reactive_load": "Ql", "shunt_susceptance": "Bsh",
        "maximum_voltage": "Vmx", "minimum_voltage": "Vmn", "from_bus": "I", "to_bus": "J", "circuit": "Nc",
        "resistance": "R", "reactance": "X", "charging": "Bshl", "rating": "MVA", "tap": "Tap", "phase_shift": "Def",
        "bus": "Bus", "identifier": "Id", "controlled_bus": "Bc", "status": "E", "control_mode": "M", "reactive_power": "Q",
        "active_power": "P",
    },
}


def convert(ntw_path: str | Path, dat_path: str | Path | None = None) -> Path:
    source = Path(ntw_path)
    parsed = NtwFileParser(source).system
    sections = _sections(parsed)
    destination = source.with_suffix(".dat") if dat_path is None else Path(dat_path)
    return write_dat(destination, source, sections, _DEFAULT_CONFIG)


def _magnitude(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(get_magnitude(value))
    except (TypeError, ValueError):
        return default


def _sections(system: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    blocks = getattr(system, "_components_by_block", {})
    buses = list(blocks.get("DBAR", []))
    result["DBAR"] = [
        {
            "number": int(bus.number), "name": bus.name, "type": _bus_type(bus.bustype),
            "area": int(getattr(bus.area, "area_number", 0) or 0), "voltage": _magnitude(bus.initial_voltage, 1.0),
            "angle": _magnitude(bus.angle), "active_generation": 0.0, "reactive_generation": 0.0,
            "active_load": 0.0, "reactive_load": 0.0, "shunt_susceptance": _magnitude(bus.shunt_susceptance),
            "maximum_voltage": _magnitude(bus.voltage_limits.max, 1.1), "minimum_voltage": _magnitude(bus.voltage_limits.min, 0.9),
        }
        for bus in buses
    ]
    for block, section in (("DCAI", "DCAI"), ("DGER", "DGER"), ("DLIN", "DLIN"), ("DLIN_TRANSFORMER", "DLIN_TRANSFORMER"), ("DSHUNT", "DSHUNT")):
        source_block = "DLIN_TRANSFORMER" if block == "DLIN_TRANSFORMER" else block
        components = list(blocks.get(source_block, []))
        rows = [_component_row(component, block) for component in components]
        if rows:
            result[section] = rows
    return result


def _bus_type(value: Any) -> int:
    label = getattr(value, "value", value)
    mapped = {"PQ": 0, "PV": 1, "REF": 2, "SLACK": 2}.get(str(label).upper())
    return mapped if mapped is not None else int(label or 0)


def _component_row(component: Any, block: str) -> dict[str, Any]:
    values = getattr(component, "ext", {}).get("ntw_values", [])
    if block == "DCAI":
        return {"bus": int(float(values[0])), "identifier": values[1], "status": int(float(values[2])), "active_power": float(values[3]), "reactive_power": float(values[4])}
    if block == "DGER":
        return {"bus": int(float(values[0])), "identifier": values[1], "active_generation": float(values[2]), "reactive_generation": float(values[3]), "maximum_reactive_generation": float(values[4]), "minimum_reactive_generation": float(values[5]), "voltage": float(values[6]), "controlled_bus": int(float(values[7])), "status": int(float(values[12]))}
    if block == "DLIN":
        return {"from_bus": int(float(values[0])), "to_bus": int(float(values[1])), "circuit": values[2], "resistance": float(values[3]), "reactance": float(values[4]), "charging": float(values[5]), "rating": float(values[6])}
    if block == "DSHUNT":
        return {"bus": int(float(values[0])), "control_mode": int(float(values[1])), "maximum_voltage": float(values[2]), "minimum_voltage": float(values[3]), "controlled_bus": int(float(values[4])), "reactive_power": float(values[5]), "status": int(float(values[6]))}
    continuation = getattr(component, "ext", {}).get("ntw_continuation_values", [])
    values = continuation[0] if continuation else []
    return {
        "from_bus": int(float(getattr(component, "from_bus", 0))),
        "to_bus": int(float(getattr(component, "to_bus", 0))),
        "circuit": values[0] if values else "1",
        "resistance": float(values[1]) if len(values) > 1 else 0.0,
        "reactance": float(values[2]) if len(values) > 2 else 0.0,
        "tap": float(values[3]) if len(values) > 3 else 1.0,
        "rating": float(values[5]) if len(values) > 5 else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert an ANAREDE NTW file to native C++ DAT format.")
    parser.add_argument("ntw")
    parser.add_argument("dat", nargs="?")
    args = parser.parse_args(argv)
    destination = convert(args.ntw, args.dat)
    print(f"Wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
