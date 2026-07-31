"""ANAREDE parser and in-memory conversion to infrasys System."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from infrasys import System
from loguru import logger

from o_grid.constants import REQUIRED_KEYS
from o_grid.models import BLOCK_BASE_CLASSES, AnaredeComponent, Arc, Area, MinMax
from o_grid.units import Voltage
from o_grid.utils.utils_parser import normalize_row

ParsedScalar: TypeAlias = int | float | str | None
MAPPING_PATH = Path(__file__).resolve().parent / "config" / "anarede_mapping.json"

DLIN_DERIVED_BLOCKS: tuple[str, ...] = ("DLIN_TAP", "DLIN_PHASE_SHIFT")
BUS_INTERNAL_GROUP_BLOCKS: tuple[str, ...] = ("DGBT", "DGLT")


@dataclass(slots=True)
class ParsedAnaredeSystem:
    """Parsed ANAREDE representation and populated infrasys system."""

    source: Path
    system: System
    components_by_block: dict[str, list[AnaredeComponent]]
    component_classes: dict[str, type[AnaredeComponent]]


class AnaredeInfrasysParser:
    """Parse ANAREDE `.pwf` files and populate an infrasys `System`."""

    def __init__(
        self, mapping_path: Path | str = MAPPING_PATH, system_name: str = "ANAREDE"
    ) -> None:
        self.mapping_path = Path(mapping_path)
        self.system_name = system_name
        self._raw_mapping = self._load_mapping(self.mapping_path)
        self.mapping = {
            section: spec
            for section, spec in self._raw_mapping.items()
            if not section.startswith("_")
        }
        self.component_classes = self._build_component_classes(self.mapping)
        dlin_fields = self.mapping.get("DLIN", {}).get("fields", {})
        if dlin_fields:
            for block in DLIN_DERIVED_BLOCKS:
                self.component_classes[block] = self._create_component_class(block, dlin_fields)
        self.dbsh_bank_fields = self.mapping.get("DBSH", {}).get("bank_fields", {})
        if self.dbsh_bank_fields:
            self.component_classes["DBSH_BANK"] = self._create_component_class(
                "DBSH_BANK", self.dbsh_bank_fields
            )

    @staticmethod
    def _load_mapping(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _build_component_classes(
        self, mapping: dict[str, Any]
    ) -> dict[str, type[AnaredeComponent]]:
        classes: dict[str, type[AnaredeComponent]] = {}
        for block, spec in mapping.items():
            base_class = BLOCK_BASE_CLASSES.get(block)
            if base_class is not None:
                classes[block] = base_class
                continue
            classes[block] = self._create_component_class(block, spec.get("fields", {}))
        return classes

    def _create_component_class(
        self, block: str, field_specs: dict[str, Any]
    ) -> type[AnaredeComponent]:
        base_class = BLOCK_BASE_CLASSES.get(block, AnaredeComponent)
        class_name = (
            base_class.__name__ if base_class is not AnaredeComponent else f"Anarede{block}"
        )
        annotations: dict[str, Any] = {}
        namespace: dict[str, Any] = {
            "__module__": __name__,
            "__annotations__": annotations,
            "block": block,
        }

        for field_name in field_specs:
            model_field_name = self._model_field_name(field_name)
            annotations[model_field_name] = ParsedScalar
            namespace[model_field_name] = None

        if block == "DBSH_BANK":
            annotations["parent_record_index"] = int | None
            namespace["parent_record_index"] = None

        component_class = type(class_name, (base_class,), namespace)
        component_class.block = block
        return component_class

    @staticmethod
    def _model_field_name(field_name: str) -> str:
        if field_name == "name":
            return "anarede_name"
        if field_name == "type":
            return "bustype"
        return field_name

    def _to_model_values(self, values: Mapping[str, ParsedScalar]) -> dict[str, ParsedScalar]:
        return {self._model_field_name(field_name): value for field_name, value in values.items()}

    def parse(self, pwf_path: Path | str) -> ParsedAnaredeSystem:
        source = Path(pwf_path)
        lines = self._read_pwf_text(source).splitlines()
        system = System(name=self.system_name)
        title_lines: list[str] = []
        components_by_block: dict[str, list[AnaredeComponent]] = {
            block: [] for block in self.component_classes
        }

        active_block: str | None = None
        current_dbsh: AnaredeComponent | None = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            section_header = self._section_header_name(stripped)
            if section_header is not None:
                active_block = section_header
                current_dbsh = None
                continue

            if active_block is None:
                continue
            if stripped.startswith("("):
                continue

            upper = stripped.upper()
            if upper == "FIM":
                break
            if upper.startswith("99999"):
                if active_block == "DBAR":
                    self._attach_bus_areas(system, components_by_block)
                active_block = None
                current_dbsh = None
                continue

            if active_block == "DBSH" and upper == "FBAN":
                current_dbsh = None
                continue

            if active_block == "TITU":
                title_line = self._parse_titu_line(line)
                if title_line:
                    title_lines.append(title_line)
                continue

            if active_block in {"DOPC", "DCTE"}:
                for record in self._parse_pair_records(active_block, line, components_by_block):
                    components_by_block[active_block].append(record)
                    self._add_component(system, record)
                continue

            if (
                active_block == "DBSH"
                and current_dbsh is not None
                and "DBSH_BANK" in self.component_classes
            ):
                bank_record = self._parse_bank_record(
                    line,
                    len(components_by_block["DBSH_BANK"]) + 1,
                    parent_record_index=current_dbsh.record_index,
                )
                components_by_block["DBSH_BANK"].append(bank_record)
                self._add_component(system, bank_record)
                continue

            record = self._parse_record(
                active_block, line, len(components_by_block[active_block]) + 1
            )
            components_by_block[active_block].append(record)

            # Keep group dictionaries internal; they are attached to ACBus records later.
            if active_block == "DLIN":
                arc = self._build_arc_from_dlin_record(record, len(components_by_block["DLIN"]))
                setattr(record, "arc", arc)
                self._add_component(system, arc)

            if active_block not in BUS_INTERNAL_GROUP_BLOCKS and active_block != "DBAR":
                if active_block != "DLIN" or not self._is_transformer_dlin_record(record):
                    self._add_component(system, record)

            if active_block == "DLIN":
                for derived in self._derive_transformer_records_from_line(
                    record,
                    components_by_block,
                ):
                    self._add_component(system, derived)

            if active_block == "DBSH":
                current_dbsh = record

        if title_lines:
            system.description = "\n".join(title_lines)

        self._attach_bus_voltage_groups(components_by_block)
        self._log_component_summary(system)

        return ParsedAnaredeSystem(
            source=source,
            system=system,
            components_by_block={k: v for k, v in components_by_block.items() if v},
            component_classes=self.component_classes,
        )

    def _add_component(self, system: System, component: AnaredeComponent) -> None:
        system.add_component(component)

    def _log_component_summary(self, system: System) -> None:
        counts: dict[str, int] = {}
        for component in system._component_mgr.iter_all():
            component_name = type(component).__name__
            counts[component_name] = counts.get(component_name, 0) + 1

        for component_name, count in counts.items():
            logger.info("Parsed {} component(s): {}", component_name, count)

    def _attach_bus_areas(
        self, system: System, components_by_block: dict[str, list[AnaredeComponent]]
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        areas_by_key: dict[str, Area] = {}
        for bus in buses:
            area_value = getattr(bus, "area", None)
            area_key = self._normalize_group_key(area_value)
            if not area_key:
                continue

            area = areas_by_key.get(area_key)
            area_number = int(float(area_key)) if self._looks_numeric(area_key) else None
            if area is None:
                area = Area(name=f"Area_{area_key}", area_number=area_number)
                areas_by_key[area_key] = area
                self._add_component(system, area)

            setattr(bus, "area", area)
            self._add_component(system, bus)
            if area_number is None:
                logger.warning("Bus {} references a non-numeric area key {}", bus.name, area_key)

    def _build_arc_from_dlin_record(self, line_record: AnaredeComponent, record_index: int) -> Arc:
        from_bus = getattr(line_record, "from_bus", None)
        to_bus = getattr(line_record, "to_bus", None)
        return Arc(
            name=f"Arc_{record_index}",
            from_to=from_bus,
            to_from=to_bus,
        )

    def _is_transformer_dlin_record(self, record: AnaredeComponent) -> bool:
        values = self._extract_dlin_values(record)
        return self._has_non_default_tap(values.get("tap")) or self._has_non_zero_angle(
            values.get("phase_shift")
        )

    def _attach_bus_voltage_groups(
        self, components_by_block: dict[str, list[AnaredeComponent]]
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        base_by_group = self._group_components_by_key(components_by_block.get("DGBT", []))
        limit_by_group = self._group_components_by_key(components_by_block.get("DGLT", []))

        for bus in buses:
            base_key = self._normalize_group_key(getattr(bus, "voltage_base_group", None))
            base_group = base_by_group.get(base_key)
            setattr(bus, "voltage_base_group_data", base_group)
            if base_group is not None:
                voltage = getattr(base_group, "voltage", None)
                setattr(
                    bus,
                    "base_voltage",
                    Voltage(voltage, "kV") if voltage is not None else None,
                )

            limit_key = self._normalize_group_key(getattr(bus, "voltage_limit_group", None))
            limit_group = limit_by_group.get(limit_key)
            setattr(bus, "voltage_limit_group_data", limit_group)
            if limit_group is not None:
                minimum_voltage_limit = getattr(limit_group, "minimum_voltage_limit", None)
                maximum_voltage_limit = getattr(limit_group, "maximum_voltage_limit", None)
                setattr(
                    bus,
                    "voltage_limits",
                    MinMax(
                        min=minimum_voltage_limit if minimum_voltage_limit is not None else 0.0,
                        max=maximum_voltage_limit if maximum_voltage_limit is not None else 0.0,
                    ),
                )

    def _group_components_by_key(
        self, components: list[AnaredeComponent]
    ) -> dict[str, AnaredeComponent]:
        grouped: dict[str, AnaredeComponent] = {}
        for component in components:
            key = self._normalize_group_key(getattr(component, "group", None))
            if key:
                grouped[key] = component
        return grouped

    @staticmethod
    def _normalize_group_key(value: ParsedScalar) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if hasattr(value, "area_number"):
            area_number = getattr(value, "area_number", None)
            if area_number is not None:
                return str(area_number).strip().upper()
        if hasattr(value, "load_zone_number"):
            load_zone_number = getattr(value, "load_zone_number", None)
            if load_zone_number is not None:
                return str(load_zone_number).strip().upper()
        if hasattr(value, "group"):
            group = getattr(value, "group", None)
            if group is not None:
                return str(group).strip().upper()
        return str(value).strip().upper()

    @staticmethod
    def _read_pwf_text(path: Path) -> str:
        return path.read_bytes().decode("cp1252", errors="replace").replace("\ufffd", "?")

    def _parse_record(self, block: str, line: str, record_index: int) -> AnaredeComponent:
        field_specs = self.mapping[block].get("fields", {})
        values = {
            name: self._parse_fixed_value(self._slice_field(line, spec), spec)
            for name, spec in field_specs.items()
        }
        if block == "DBAR":
            values = self._repair_dbar_values(line, field_specs, values)

        model = self.component_classes[block]
        record_data: dict[str, Any] = {
            "name": self._component_name(block, record_index, values),
            "record_index": record_index,
            **self._to_model_values(values),
        }
        return model(**record_data)

    def _parse_bank_record(
        self, line: str, record_index: int, parent_record_index: int
    ) -> AnaredeComponent:
        values = {
            name: self._parse_fixed_value(self._slice_field(line, spec), spec)
            for name, spec in self.dbsh_bank_fields.items()
        }
        values["parent_record_index"] = parent_record_index
        model = self.component_classes["DBSH_BANK"]
        record_data: dict[str, Any] = {
            "name": self._component_name("DBSH_BANK", record_index, values),
            "record_index": record_index,
            **self._to_model_values(values),
        }
        return model(**record_data)

    def _derive_transformer_records_from_line(
        self,
        line_record: AnaredeComponent,
        components_by_block: dict[str, list[AnaredeComponent]],
    ) -> list[AnaredeComponent]:
        values = self._extract_dlin_values(line_record)
        records: list[AnaredeComponent] = []

        if self._has_non_default_tap(values.get("tap")) and "DLIN_TAP" in self.component_classes:
            record_index = len(components_by_block["DLIN_TAP"]) + 1
            component = self._build_dlin_derived_record(
                block="DLIN_TAP",
                values=values,
                record_index=record_index,
            )
            components_by_block["DLIN_TAP"].append(component)
            records.append(component)

        if (
            self._has_non_zero_angle(values.get("phase_shift"))
            and "DLIN_PHASE_SHIFT" in self.component_classes
        ):
            record_index = len(components_by_block["DLIN_PHASE_SHIFT"]) + 1
            component = self._build_dlin_derived_record(
                block="DLIN_PHASE_SHIFT",
                values=values,
                record_index=record_index,
            )
            components_by_block["DLIN_PHASE_SHIFT"].append(component)
            records.append(component)

        return records

    def _extract_dlin_values(self, line_record: AnaredeComponent) -> dict[str, ParsedScalar]:
        dlin_fields = self.mapping.get("DLIN", {}).get("fields", {})
        values: dict[str, ParsedScalar] = {}
        for field_name in dlin_fields:
            attr_name = self._model_field_name(field_name)
            values[field_name] = getattr(line_record, attr_name, None)
        return values

    def _build_dlin_derived_record(
        self,
        block: str,
        values: dict[str, ParsedScalar],
        record_index: int,
    ) -> AnaredeComponent:
        model = self.component_classes[block]
        record_data: dict[str, Any] = {
            "name": self._component_name(block, record_index, values),
            "record_index": record_index,
            **self._to_model_values(values),
        }
        return model(**record_data)

    @staticmethod
    def _has_non_default_tap(value: ParsedScalar) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, (int, float)):
            return abs(float(value) - 1.0) > 1e-9
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return False
            if AnaredeInfrasysParser._looks_numeric(stripped):
                return abs(float(stripped) - 1.0) > 1e-9
            return True
        return False

    @staticmethod
    def _has_non_zero_angle(value: ParsedScalar) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, (int, float)):
            return abs(float(value)) > 1e-9
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return False
            if AnaredeInfrasysParser._looks_numeric(stripped):
                return abs(float(stripped)) > 1e-9
            return False
        return False

    def _parse_pair_records(
        self,
        block: str,
        line: str,
        components_by_block: dict[str, list[AnaredeComponent]],
    ) -> list[AnaredeComponent]:
        tokens = line.split()
        if len(tokens) < 2:
            return []

        left_field, right_field = ("option", "state") if block == "DOPC" else ("mnemonic", "value")
        records: list[AnaredeComponent] = []
        model = self.component_classes[block]
        for i in range(0, len(tokens) - 1, 2):
            value: ParsedScalar = tokens[i + 1]
            if block == "DCTE" and self._looks_numeric(str(value)):
                value = self._parse_numeric(str(value), decimal_places=None)
            record_index = len(components_by_block[block]) + len(records) + 1
            values = {left_field: tokens[i], right_field: value}
            record_data: dict[str, Any] = {
                "name": self._component_name(block, record_index, values),
                "record_index": record_index,
                **self._to_model_values(values),
            }
            records.append(model(**record_data))
        return records

    @staticmethod
    def _slice_field(line: str, field_spec: dict[str, Any]) -> str:
        column = field_spec.get("column", {})
        start = int(column.get("start", 1)) - 1
        end = int(column.get("end", start + 1))
        if start >= len(line):
            return ""
        return line[start:end]

    def _parse_titu_line(self, line: str) -> str:
        field_specs = self.mapping.get("TITU", {}).get("fields", {})
        title_spec = field_specs.get("title_line")
        if not title_spec:
            return line.strip()
        value = self._parse_fixed_value(self._slice_field(line, title_spec), title_spec)
        return "" if value is None else str(value).strip()

    def _parse_fixed_value(self, raw: str, field_spec: dict[str, Any]) -> ParsedScalar:
        text = raw.strip()
        if not text:
            default = field_spec.get("default")
            return None if default == "" else default

        if self._looks_numeric(text):
            decimal_places = self._implicit_decimal_places(field_spec)
            return self._parse_numeric(text, decimal_places)
        return text.replace("\ufffd", "?")

    @staticmethod
    def _parse_numeric(text: str, decimal_places: int | None) -> int | float:
        if decimal_places is not None and "." not in text and "e" not in text.lower():
            return float(text) / (10**decimal_places)
        number = float(text)
        if number.is_integer() and "." not in text and "e" not in text.lower():
            return int(number)
        return number

    @staticmethod
    def _looks_numeric(value: str) -> bool:
        return bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", value))

    @staticmethod
    def _implicit_decimal_places(field_spec: dict[str, Any]) -> int | None:
        description = field_spec.get("description", "")
        column = field_spec.get("column", {})
        match = re.search(
            r"Implicit decimal point between columns (\d+) and (\d+)", description, re.IGNORECASE
        )
        if not match:
            return None
        decimal_column = int(match.group(1))
        end = int(column.get("end", decimal_column))
        return max(0, end - decimal_column)

    @staticmethod
    def _repair_dbar_values(
        line: str, field_specs: dict[str, Any], values: dict[str, ParsedScalar]
    ) -> dict[str, ParsedScalar]:
        voltage = values.get("voltage")
        if voltage is None or isinstance(voltage, (int, float)):
            return values
        packed = line[22:30].strip() if len(line) > 22 else ""
        match = re.fullmatch(r"([+-]?\d{3,4})([+-](?:\d+(?:\.\d*)?|\.\d+))", packed)
        if not match:
            return values

        repaired = dict(values)
        repaired["voltage"] = AnaredeInfrasysParser._parse_numeric(match.group(1), decimal_places=3)
        repaired["angle"] = AnaredeInfrasysParser._parse_numeric(
            match.group(2), decimal_places=None
        )
        repaired["voltage_limit_group"] = field_specs.get("voltage_limit_group", {}).get("default")
        return repaired

    def _section_header_name(self, stripped: str) -> str | None:
        upper = stripped.upper()
        if upper in self.mapping:
            return upper

        tokens = upper.split()
        if len(tokens) > 1 and tokens[0] == "DTPF" and tokens[1] == "CIRC":
            return "DTPF_CIRC"

        if tokens and tokens[0] in self.mapping and tokens[0] in {"DOPC"}:
            return tokens[0]
        return None

    def _component_name(
        self, block: str, record_index: int, values: Mapping[str, ParsedScalar]
    ) -> str:
        for key in (
            "name",
            "anarede_name",
            "number",
            "bus",
            "from_bus",
            "dc_bus",
            "mnemonic",
            "option",
        ):
            value = values.get(key)
            if value is not None and str(value).strip():
                token = re.sub(r"\s+", "_", str(value).strip())
                return f"{token}_{record_index}"
        return f"{block}_{record_index}"


def parse_anarede_system(
    pwf_path: Path | str,
    mapping_path: Path | str = MAPPING_PATH,
    system_name: str = "ANAREDE",
) -> ParsedAnaredeSystem:
    """Parse an ANAREDE `.pwf` and return a populated infrasys representation."""
    parser = AnaredeInfrasysParser(mapping_path=mapping_path, system_name=system_name)
    return parser.parse(pwf_path)


def parse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse and validate generic rows for basic package compatibility."""
    return [normalize_row(row, REQUIRED_KEYS) for row in rows]
