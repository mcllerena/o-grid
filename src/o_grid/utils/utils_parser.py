"""Parser utility helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeAlias

from infrasys import Component

from o_grid.units import get_magnitude

ParsedScalar: TypeAlias = int | float | str | None


def to_float(value: Any) -> float:
    """Convert a supported value to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return float(stripped)
    raise TypeError(f"unsupported value type: {type(value)!r}")


def normalize_row(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Validate and normalize a row used by parsers."""
    missing = [key for key in keys if key not in row]
    if missing:
        raise KeyError(f"missing keys: {', '.join(missing)}")

    normalized = dict(row)
    normalized["load_mw"] = to_float(normalized["load_mw"])
    normalized["generator_mw"] = to_float(normalized["generator_mw"])
    return normalized


def load_mapping(path: Path) -> dict[str, Any]:
    """Load an ANAREDE field-mapping JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def read_pwf_text(path: Path) -> str:
    """Read a `.pwf` file using ANAREDE's cp1252 encoding."""
    return path.read_bytes().decode("cp1252", errors="replace").replace("\ufffd", "?")


def model_field_name(block: str, field_name: str) -> str:
    """Map an ANAREDE field name to its concrete model attribute name."""
    if field_name == "name" and block in {"DBAR", "DARE", "DELO"}:
        return "anarede_name"
    if field_name == "type" and block == "DBAR":
        return "bustype"
    if field_name == "dlin_circuit":
        return "line_circuit"
    return field_name


def normalize_group_key(value: ParsedScalar) -> str:
    """Normalize a value used to group or cross-reference components."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if hasattr(value, "area_number"):
        area_number = getattr(value, "area_number", None)
        if area_number is not None:
            return str(area_number).strip().upper()
    if hasattr(value, "group"):
        group = getattr(value, "group", None)
        if group is not None:
            return str(group).strip().upper()
    return str(value).strip().upper()


def looks_numeric(value: str) -> bool:
    """Return whether a raw token represents a number."""
    return bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", value))


def parse_numeric(text: str, decimal_places: int | None) -> int | float:
    """Parse a numeric token, honoring any implicit decimal point."""
    if decimal_places is not None and "." not in text and "e" not in text.lower():
        return float(text) / (10**decimal_places)
    number = float(text)
    if number.is_integer() and "." not in text and "e" not in text.lower():
        return int(number)
    return number


def implicit_decimal_places(field_spec: dict[str, Any]) -> int | None:
    """Return the implicit decimal-place count declared for a fixed field."""
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


def slice_field(line: str, field_spec: dict[str, Any]) -> str:
    """Slice a fixed-width field out of a record line."""
    column = field_spec.get("column", {})
    start = int(column.get("start", 1)) - 1
    end = int(column.get("end", start + 1))
    if start >= len(line):
        return ""
    return line[start:end]


def parse_fixed_value(raw: str, field_spec: dict[str, Any]) -> ParsedScalar:
    """Parse a single fixed-width field value."""
    text = raw.strip()
    if not text:
        default = field_spec.get("default")
        return None if default == "" else default

    if looks_numeric(text):
        decimal_places = implicit_decimal_places(field_spec)
        return parse_numeric(text, decimal_places)
    return text.replace("\ufffd", "?")


def component_name(block: str, record_index: int, values: Mapping[str, ParsedScalar]) -> str:
    """Build a component name from the most identifying field available."""
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


def attach_raw_component_metadata(
    component: Component,
    raw_line: str,
    raw_values: Mapping[str, ParsedScalar],
) -> None:
    """Store the raw parsed values on a component's ``ext`` dictionary."""
    component_ext = getattr(component, "ext", None)
    if isinstance(component_ext, dict):
        component_ext["pwf_values"] = dict(raw_values)


def map_anarede_state_to_available(
    values: dict[str, ParsedScalar],
) -> dict[str, ParsedScalar]:
    """Translate ANAREDE operation/state fields into an ``available`` flag."""
    mapped = dict(values)
    mapped.pop("operation", None)
    state = mapped.pop("state", None)
    if state is None:
        return mapped

    state_text = str(state).strip().upper()
    if state_text == "D":
        mapped["available"] = False
    elif state_text == "L" or state_text == "":
        mapped["available"] = True
    else:
        mapped["available"] = True
    return mapped


def normalize_dbar_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DBAR fields and rename the initial voltage."""
    normalized = dict(values)
    for field_name in ("operation", "state", "visualization_mode", "load_zone"):
        normalized.pop(field_name, None)

    if "voltage" in normalized:
        normalized["initial_voltage"] = normalized.pop("voltage")
    return normalized


def normalize_dlin_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop DLIN fields represented elsewhere on the branch models."""
    normalized = dict(values)
    for field_name in (
        "equipment_capacity",
        "maneuverable",
        "operation",
        "state",
        "phase_shift",
        "resistance",
        "reactance",
        "susceptance",
        "tap",
        "tap_maximum",
        "tap_minimum",
    ):
        normalized.pop(field_name, None)
    return normalized


def normalize_dcba_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DCBA fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    normalized.pop("voltage_limit_group", None)
    return normalized


def normalize_dccv_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DCCV fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def normalize_dcnv_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DCNV fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def normalize_dcli_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DCLI fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def normalize_delo_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DELO fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def normalize_dger_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DGER fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def normalize_dshl_values(values: dict[str, ParsedScalar]) -> dict[str, ParsedScalar]:
    """Drop unused DSHL fields."""
    normalized = dict(values)
    normalized.pop("operation", None)
    return normalized


def coerce_circuit_number(value: ParsedScalar) -> int | None:
    """Coerce a DCLI circuit token to an integer, or ``None`` when blank."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def default_dcli_circuit(operation: ParsedScalar, existing: set[int]) -> int:
    """Return the default DCLI circuit number for the given operation."""
    # Modification (M/2) defaults to the lowest parallel circuit; addition (A/0/blank)
    # takes the first free number above the highest existing parallel circuit.
    if str(operation).strip().upper() in {"M", "2"}:
        return min(existing) if existing else 1
    return max(existing) + 1 if existing else 1


def has_non_default_tap(value: ParsedScalar) -> bool:
    """Return whether a DLIN tap value differs from the default (1.0)."""
    if value is None or value == "":
        return False
    if hasattr(value, "magnitude"):
        value = get_magnitude(value)
    if isinstance(value, (int, float)):
        return abs(float(value) - 1.0) > 1e-9
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        if looks_numeric(stripped):
            return abs(float(stripped) - 1.0) > 1e-9
        return True
    return False


def has_non_zero_angle(value: ParsedScalar) -> bool:
    """Return whether a DLIN phase-shift value is non-zero."""
    if value is None or value == "":
        return False
    if hasattr(value, "magnitude"):
        value = get_magnitude(value)
    if isinstance(value, (int, float)):
        return abs(float(value)) > 1e-9
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        if looks_numeric(stripped):
            return abs(float(stripped)) > 1e-9
        return False
    return False


def has_tap_value(value: ParsedScalar) -> bool:
    """Return whether a DLIN tap field carries any value (even the fixed 1.0 ratio)."""
    if value is None:
        return False
    if hasattr(value, "magnitude"):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    return False


def has_tap_range(minimum: ParsedScalar, maximum: ParsedScalar) -> bool:
    """Return whether a DLIN record defines a tap range (min or max present)."""
    return has_tap_value(minimum) or has_tap_value(maximum)


def _abs_magnitude_or_zero(value: ParsedScalar) -> float:
    """Return the absolute numeric magnitude of a scalar, or 0.0 when unavailable."""
    if value is None or value == "":
        return 0.0
    if hasattr(value, "magnitude"):
        value = get_magnitude(value)
    if isinstance(value, (int, float)):
        return abs(float(value))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and looks_numeric(stripped):
            return abs(float(stripped))
    return 0.0


def is_switch_impedance(
    resistance: ParsedScalar,
    reactance: ParsedScalar,
    susceptance: ParsedScalar,
    threshold: float,
) -> bool:
    """Return whether a DLIN branch has switch-level (near-zero) impedance and shunt."""
    return (
        _abs_magnitude_or_zero(resistance) <= threshold
        and _abs_magnitude_or_zero(reactance) <= threshold
        and _abs_magnitude_or_zero(susceptance) <= threshold
    )


def repair_dbar_values(
    line: str, field_specs: dict[str, Any], values: dict[str, ParsedScalar]
) -> dict[str, ParsedScalar]:
    """Repair a DBAR record whose voltage/angle fields ran together."""
    voltage = values.get("voltage")
    if voltage is None or isinstance(voltage, (int, float)):
        return values
    packed = line[22:30].strip() if len(line) > 22 else ""
    match = re.fullmatch(r"([+-]?\d{3,4})([+-](?:\d+(?:\.\d*)?|\.\d+))", packed)
    if not match:
        return values

    repaired = dict(values)
    repaired["voltage"] = parse_numeric(match.group(1), decimal_places=3)
    repaired["angle"] = parse_numeric(match.group(2), decimal_places=None)
    repaired["voltage_limit_group"] = field_specs.get("voltage_limit_group", {}).get("default")
    return repaired
