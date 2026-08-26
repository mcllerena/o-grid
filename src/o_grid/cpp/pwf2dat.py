"""Convert ANAREDE fixed-width PWF files to native C++ DAT files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from o_grid.constants import MAPPING_PATH
from o_grid.cpp.dat_writer import write_dat
from o_grid.utils.utils_parser import load_mapping, parse_fixed_value, read_pwf_text, slice_field


def convert(
    pwf_path: str | Path,
    dat_path: str | Path | None = None,
    mapping_path: str | Path = MAPPING_PATH,
) -> Path:
    source = Path(pwf_path)
    mapping = load_mapping(Path(mapping_path))
    sections = _parse(source, mapping)
    destination = source.with_suffix(".dat") if dat_path is None else Path(dat_path)
    return write_dat(destination, source, sections, mapping.get("_dat", {}))


def _parse(source: Path, mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    sections = {name: [] for name in mapping if not name.startswith("_")}
    sections.setdefault("DBSH_BANK", [])
    active: str | None = None
    parent_index = 0
    for line in read_pwf_text(source).splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if not stripped:
            continue
        if upper in sections:
            active = upper
            continue
        if active == "DBSH" and upper == "FBAN":
            active = None
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9]{3,4}", upper):
            active = upper if upper in sections else None
            continue
        if active is None or stripped.startswith("(") or upper.startswith("99999"):
            continue
        if active in {"DOPC", "DCTE"}:
            tokens = stripped.split()
            key = "option" if active == "DOPC" else "mnemonic"
            value_key = "state" if active == "DOPC" else "value"
            for index in range(0, len(tokens) - 1, 2):
                value: Any = tokens[index + 1]
                if active == "DCTE":
                    try:
                        value = float(value)
                        value = int(value) if value.is_integer() else value
                    except ValueError:
                        pass
                sections[active].append({key: tokens[index], value_key: value})
            continue
        fields = mapping[active].get("fields", {})
        values = {
            name: parse_fixed_value(slice_field(line, spec), spec) for name, spec in fields.items()
        }
        if active == "DBSH":
            sections[active].append(values)
            parent_index = len(sections[active])
        elif active == "DBSH_BANK":
            values["parent_record_index"] = parent_index
            sections[active].append(values)
        else:
            sections[active].append(values)
    return {name: records for name, records in sections.items() if records}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert an ANAREDE PWF file to native C++ DAT format."
    )
    parser.add_argument("pwf")
    parser.add_argument("dat", nargs="?")
    parser.add_argument("--mapping", default=str(MAPPING_PATH))
    args = parser.parse_args(argv)
    destination = convert(args.pwf, args.dat, args.mapping)
    print(f"Wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
