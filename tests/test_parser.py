from __future__ import annotations

import pytest

from o_grid import export_rows, parse_rows
from o_grid.constants import REQUIRED_KEYS
from o_grid.utils.utils_exporter import format_row
from o_grid.utils.utils_parser import normalize_row, to_float


def test_constants_contract() -> None:
    assert REQUIRED_KEYS == ("bus", "load_mw", "generator_mw")


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
        normalize_row({"bus": "A", "load_mw": 1.0}, REQUIRED_KEYS)


def test_parse_rows_normalizes_all_rows() -> None:
    rows = [
        {"bus": "A", "load_mw": "1", "generator_mw": "1.5"},
        {"bus": "B", "load_mw": 2, "generator_mw": 2.5},
    ]
    parsed = parse_rows(rows)

    assert parsed == [
        {"bus": "A", "load_mw": 1.0, "generator_mw": 1.5},
        {"bus": "B", "load_mw": 2.0, "generator_mw": 2.5},
    ]


def test_format_row_is_stable_and_sorted() -> None:
    row = {"bus": "A", "generator_mw": 5.0, "load_mw": 3.0}
    assert format_row(row) == "A,5.0,3.0"


def test_export_rows_uses_separator() -> None:
    rows = [
        {"bus": "A", "generator_mw": 5.0, "load_mw": 3.0},
        {"bus": "B", "generator_mw": 1.0, "load_mw": 2.0},
    ]
    text = export_rows(rows, separator=";")

    assert text == "A;5.0;3.0\nB;1.0;2.0"
