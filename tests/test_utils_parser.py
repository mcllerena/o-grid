"""Tests for parser utility helpers in ``o_grid.utils.utils_parser``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from o_grid.constants import REQUIRED_KEYS
from o_grid.units import ActivePower
from o_grid.utils.utils_parser import (
    attach_raw_component_metadata,
    coerce_circuit_number,
    component_name,
    default_dcli_circuit,
    has_non_default_tap,
    has_non_zero_angle,
    has_tap_range,
    has_tap_value,
    implicit_decimal_places,
    is_switch_impedance,
    load_mapping,
    looks_numeric,
    map_anarede_state_to_available,
    model_field_name,
    normalize_dbar_values,
    normalize_dcba_values,
    normalize_dccv_values,
    normalize_dcli_values,
    normalize_dcnv_values,
    normalize_delo_values,
    normalize_dger_values,
    normalize_dlin_values,
    normalize_dshl_values,
    normalize_group_key,
    normalize_row,
    parse_fixed_value,
    parse_numeric,
    read_pwf_text,
    repair_dbar_values,
    slice_field,
    to_float,
)


class _FakeComponent:
    """Minimal stand-in exposing an ``ext`` mapping."""

    def __init__(self, ext: object) -> None:
        self.ext = ext


def test_to_float_handles_numeric_and_string_values() -> None:
    assert to_float(1) == 1.0
    assert to_float(2.5) == 2.5
    assert to_float("3.2") == 3.2


def test_to_float_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        to_float("  ")


def test_to_float_rejects_unsupported_types() -> None:
    with pytest.raises(TypeError):
        to_float([1, 2, 3])


def test_normalize_row_converts_numeric_fields() -> None:
    row = {"bus": "A", "load_mw": "2.0", "generator_mw": 3}
    normalized = normalize_row(row, REQUIRED_KEYS)

    assert normalized["bus"] == "A"
    assert normalized["load_mw"] == 2.0
    assert normalized["generator_mw"] == 3.0


def test_normalize_row_missing_keys_error() -> None:
    with pytest.raises(KeyError):
        normalize_row({"bus": "A"}, REQUIRED_KEYS)


def test_load_mapping_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"DBAR": {"fields": {}}}), encoding="utf-8")

    assert load_mapping(path) == {"DBAR": {"fields": {}}}


def test_read_pwf_text_decodes_cp1252(tmp_path: Path) -> None:
    path = tmp_path / "case.pwf"
    path.write_bytes("SÃO".encode("cp1252"))

    assert read_pwf_text(path) == "SÃO"


def test_read_pwf_text_replaces_invalid_bytes(tmp_path: Path) -> None:
    path = tmp_path / "case.pwf"
    path.write_bytes(b"AB\x81CD")

    assert read_pwf_text(path) == "AB?CD"


@pytest.mark.parametrize(
    ("block", "field_name", "expected"),
    [
        ("DBAR", "name", "anarede_name"),
        ("DARE", "name", "anarede_name"),
        ("DELO", "name", "anarede_name"),
        ("DBAR", "type", "bustype"),
        ("DLIN", "dlin_circuit", "line_circuit"),
        ("DLIN", "resistance", "resistance"),
        ("DCBA", "name", "name"),
    ],
)
def test_model_field_name(block: str, field_name: str, expected: str) -> None:
    assert model_field_name(block, field_name) == expected


def test_normalize_group_key_variants() -> None:
    assert normalize_group_key(None) == ""
    assert normalize_group_key(3.0) == "3"
    assert normalize_group_key(" a1 ") == "A1"


def test_normalize_group_key_reads_area_number() -> None:
    class _Area:
        area_number = 7

    assert normalize_group_key(_Area()) == "7"


def test_normalize_group_key_reads_group() -> None:
    class _Group:
        group = "gg"

    assert normalize_group_key(_Group()) == "GG"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10", True),
        ("-3.5", True),
        ("1e3", True),
        (".5", True),
        ("abc", False),
        ("", False),
        ("1.2.3", False),
    ],
)
def test_looks_numeric(value: str, expected: bool) -> None:
    assert looks_numeric(value) is expected


def test_parse_numeric_applies_implicit_decimal() -> None:
    assert parse_numeric("1234", 2) == 12.34


def test_parse_numeric_returns_int_for_whole_numbers() -> None:
    result = parse_numeric("42", None)
    assert result == 42
    assert isinstance(result, int)


def test_parse_numeric_returns_float_for_decimals() -> None:
    assert parse_numeric("3.14", None) == 3.14


def test_implicit_decimal_places_from_description() -> None:
    field_spec = {
        "description": "Implicit decimal point between columns 5 and 6",
        "column": {"end": 7},
    }
    assert implicit_decimal_places(field_spec) == 2


def test_implicit_decimal_places_without_description() -> None:
    assert implicit_decimal_places({"description": "", "column": {}}) is None


def test_slice_field_extracts_columns() -> None:
    line = "ABCDEFGHIJ"
    assert slice_field(line, {"column": {"start": 3, "end": 5}}) == "CDE"


def test_slice_field_beyond_line_returns_empty() -> None:
    assert slice_field("AB", {"column": {"start": 10, "end": 12}}) == ""


def test_parse_fixed_value_numeric() -> None:
    field_spec = {"column": {"start": 1, "end": 4}}
    assert parse_fixed_value(" 42 ", field_spec) == 42


def test_parse_fixed_value_uses_default_when_blank() -> None:
    assert parse_fixed_value("   ", {"default": 5}) == 5
    assert parse_fixed_value("   ", {"default": ""}) is None


def test_parse_fixed_value_returns_stripped_text() -> None:
    assert parse_fixed_value(" name ", {}) == "name"


def test_component_name_prefers_identifying_field() -> None:
    assert component_name("DBAR", 3, {"number": 12}) == "12_3"
    assert component_name("DBAR", 4, {"anarede_name": "Sub A"}) == "Sub_A_4"


def test_component_name_falls_back_to_block() -> None:
    assert component_name("DLIN", 2, {"other": None}) == "DLIN_2"


def test_attach_raw_component_metadata_stores_values() -> None:
    component = _FakeComponent(ext={})
    attach_raw_component_metadata(component, "raw line", {"a": 1})

    assert component.ext == {"pwf_values": {"a": 1}}


def test_attach_raw_component_metadata_ignores_non_dict_ext() -> None:
    component = _FakeComponent(ext=None)
    attach_raw_component_metadata(component, "raw line", {"a": 1})

    assert component.ext is None


@pytest.mark.parametrize(
    ("state", "expected"),
    [("D", False), ("L", True), ("", True), ("X", True)],
)
def test_map_anarede_state_to_available(state: str, expected: bool) -> None:
    mapped = map_anarede_state_to_available({"state": state, "operation": "A"})
    assert mapped["available"] is expected
    assert "operation" not in mapped
    assert "state" not in mapped


def test_map_anarede_state_to_available_without_state() -> None:
    mapped = map_anarede_state_to_available({"operation": "A"})
    assert "available" not in mapped


def test_normalize_dbar_values_drops_and_renames() -> None:
    normalized = normalize_dbar_values(
        {"operation": "A", "state": "L", "voltage": 1.0, "number": 5}
    )
    assert normalized == {"initial_voltage": 1.0, "number": 5}


def test_normalize_dlin_values_drops_fields() -> None:
    normalized = normalize_dlin_values({"resistance": 1, "reactance": 2, "from_bus": 9})
    assert normalized == {"from_bus": 9}


def test_normalize_dc_block_values_drop_operation() -> None:
    assert normalize_dcba_values({"operation": "A", "voltage_limit_group": 1, "x": 2}) == {"x": 2}
    assert normalize_dccv_values({"operation": "A", "x": 2}) == {"x": 2}
    assert normalize_dcnv_values({"operation": "A", "x": 2}) == {"x": 2}
    assert normalize_dcli_values({"operation": "A", "x": 2}) == {"x": 2}
    assert normalize_delo_values({"operation": "A", "x": 2}) == {"x": 2}
    assert normalize_dger_values({"operation": "A", "x": 2}) == {"x": 2}
    assert normalize_dshl_values({"operation": "A", "x": 2}) == {"x": 2}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("  ", None), ("3", 3), ("2.0", 2), ("abc", None)],
)
def test_coerce_circuit_number(value: object, expected: int | None) -> None:
    assert coerce_circuit_number(value) == expected  # type: ignore[arg-type]


def test_default_dcli_circuit_addition() -> None:
    assert default_dcli_circuit("A", set()) == 1
    assert default_dcli_circuit("A", {1, 2}) == 3
    assert default_dcli_circuit(None, {5}) == 6


def test_default_dcli_circuit_modification() -> None:
    assert default_dcli_circuit("M", set()) == 1
    assert default_dcli_circuit("M", {2, 4}) == 2
    assert default_dcli_circuit("2", {3, 7}) == 3


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        (1.0, False),
        (1.05, True),
        ("1.0", False),
        ("1.5", True),
        ("R", True),
    ],
)
def test_has_non_default_tap(value: object, expected: bool) -> None:
    assert has_non_default_tap(value) is expected  # type: ignore[arg-type]


def test_has_non_default_tap_reads_quantity() -> None:
    assert has_non_default_tap(ActivePower(2.0, "MW")) is True
    assert has_non_default_tap(ActivePower(1.0, "MW")) is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        (0.0, False),
        (1.5, True),
        ("0", False),
        ("2.0", True),
        ("abc", False),
    ],
)
def test_has_non_zero_angle(value: object, expected: bool) -> None:
    assert has_non_zero_angle(value) is expected  # type: ignore[arg-type]


def test_has_non_zero_angle_reads_quantity() -> None:
    assert has_non_zero_angle(ActivePower(0.0, "MW")) is False
    assert has_non_zero_angle(ActivePower(5.0, "MW")) is True


def test_repair_dbar_values_splits_packed_voltage_angle() -> None:
    line = " " * 22 + "1050-3.5" + " " * 10
    field_specs = {"voltage_limit_group": {"default": 1}}
    repaired = repair_dbar_values(line, field_specs, {"voltage": "1050-3.5"})

    assert repaired["voltage"] == 1.05
    assert repaired["angle"] == -3.5
    assert repaired["voltage_limit_group"] == 1


def test_repair_dbar_values_returns_input_when_numeric() -> None:
    values = {"voltage": 1.0}
    assert repair_dbar_values("", {}, values) is values


def test_repair_dbar_values_returns_input_without_match() -> None:
    values = {"voltage": "not-packed"}
    assert repair_dbar_values(" " * 22 + "xxxx", {}, values) is values


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (1.05, True),
        (3, True),
        ("abc", True),
        (object(), False),
    ],
)
def test_has_tap_value(value: object, expected: bool) -> None:
    assert has_tap_value(value) is expected  # type: ignore[arg-type]


def test_has_tap_value_reads_quantity() -> None:
    assert has_tap_value(ActivePower(2.0, "MW")) is True


def test_has_tap_range_detects_present_values() -> None:
    assert has_tap_range(None, 1.05) is True
    assert has_tap_range("", "") is False


@pytest.mark.parametrize(
    ("resistance", "reactance", "susceptance", "expected"),
    [
        (None, "", ActivePower(0.0, "MW"), True),
        (0.0, 0.0, 0.0, True),
        ("abc", "abc", "abc", True),
        (1.0, 0.0, 0.0, False),
    ],
)
def test_is_switch_impedance(
    resistance: object, reactance: object, susceptance: object, expected: bool
) -> None:
    assert is_switch_impedance(resistance, reactance, susceptance, 0.001) is expected  # type: ignore[arg-type]
