from __future__ import annotations

from pathlib import Path

import pytest
from infrasys import System

from o_grid import export_rows, parse_rows
from o_grid.constants import REQUIRED_KEYS
from o_grid.models import (
    ACBranch,
    ACBus,
    ACLine,
    Arc,
    Area,
    Branch,
    BusShunt,
    ControllableSeriesCompensator,
    Line,
    LineShunt,
    PhaseShiftingTransformer,
    StaticVARCompensator,
    TapChangingTransformer,
    TapTransformer,
    TapTransformerControl,
    VoltageBaseGroup,
    VoltageLimitGroup,
)
from o_grid.parser import AnaredeInfrasysParser, parse_anarede_system
from o_grid.utils.utils_exporter import format_row
from o_grid.utils.utils_parser import normalize_row, to_float

DATA_DIR = Path(__file__).resolve().parent / "data" / "anarede"


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


def test_models_package_exports_expected_types() -> None:
    assert ACBus.__name__ == "ACBus"
    assert ACLine.__name__ == "ACLine"
    assert Branch.__name__ == "Branch"
    assert ACBranch.__name__ == "ACBranch"
    assert Line.__name__ == "Line"
    assert BusShunt.__name__ == "BusShunt"
    assert LineShunt.__name__ == "LineShunt"
    assert TapChangingTransformer.__name__ == "TapTransformer"
    assert TapTransformer.__name__ == "TapTransformer"
    assert PhaseShiftingTransformer.__name__ == "PhaseShiftingTransformer"
    assert StaticVARCompensator.__name__ == "StaticVARCompensator"
    assert ControllableSeriesCompensator.__name__ == "ControllableSeriesCompensator"
    assert TapTransformerControl.__name__ == "TapTransformerControl"


def test_acline_follows_branch_hierarchy() -> None:
    assert issubclass(ACLine, Line)
    assert issubclass(Line, ACBranch)
    assert issubclass(ACBranch, Branch)


def test_example_helpers_expose_public_class_types() -> None:
    assert Branch.example().class_type == "Branch"
    assert Line.example().class_type == "Line"
    assert ACBus.example().class_type == "ACBus"
    assert Area.example().class_type == "Area"


def test_parser_attach_bus_areas_and_build_arc() -> None:
    parser = AnaredeInfrasysParser()
    system = System(name="demo")
    bus = ACBus(number=1, name="Bus-1", area=1)
    parser._attach_bus_areas(system, {"DBAR": [bus]})

    assert len(list(system.get_components(Area))) == 1
    assert len(list(system.get_components(ACBus))) == 1
    assert isinstance(bus.area, Area)

    line = ACLine(name="Line-1", from_bus=1, to_bus=2)
    arc = parser._build_arc_from_dlin_record(line, 3)
    assert arc.name == "Arc_3"
    assert arc.from_to == 1
    assert arc.to_from == 2


def test_parse_anarede_d9nodes_to_infrasys() -> None:
    parser = AnaredeInfrasysParser()
    parsed = parser.parse(DATA_DIR / "d_9nodes.pwf")

    assert "DBAR" in parsed.components_by_block
    assert "DLIN" in parsed.components_by_block
    assert len(parsed.components_by_block["DBAR"]) == 9
    assert len(parsed.components_by_block["DLIN"]) == 10

    ac_bus_type = parsed.component_classes["DBAR"]
    ac_line_type = parsed.component_classes["DLIN"]
    assert ac_bus_type.__name__ == "ACBus"
    assert ac_line_type.__name__ == "ACLine"
    assert issubclass(ac_bus_type, ACBus)
    assert issubclass(ac_line_type, ACLine)

    assert len(list(parsed.system.get_components(ac_bus_type))) == 9
    assert len(list(parsed.system.get_components(ac_line_type))) == 10
    assert len(list(parsed.system.get_components(Area))) == 1
    assert len(list(parsed.system.get_components(Arc))) == 10

    assert len(list(parsed.system.get_components(parsed.component_classes["DGBT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DGLT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DLIN_TAP"]))) == 0

    buses = parsed.components_by_block["DBAR"]
    assert all(isinstance(bus, ACBus) for bus in buses)
    assert buses[1].name == "BAR-2_GER2_2"
    assert buses[1].bus_type == 1
    assert buses[0].bus_type == 2
    assert buses[2].bus_type == 0
    assert all(getattr(component, "uuid", None) is not None for component in buses)
    assert all(bus.voltage_base_group_data is not None for bus in buses)
    assert all(bus.voltage_limit_group_data is not None for bus in buses)
    assert all(isinstance(bus.voltage_base_group_data, VoltageBaseGroup) for bus in buses)
    assert all(isinstance(bus.voltage_limit_group_data, VoltageLimitGroup) for bus in buses)

    line = parsed.components_by_block["DLIN"][0]
    assert not line.name.startswith("ACLine_")
    assert getattr(line, "uuid", None) is not None

    assert "TITU" not in parsed.components_by_block
    assert parsed.system.description == "Sistema-Teste de 9 Barras - Caso Inicial"


def test_parse_anarede_dcer_dcsc_blocks() -> None:
    parsed = parse_anarede_system(DATA_DIR / "d_33nodes_dcer_dcsc.pwf")

    assert len(parsed.components_by_block["DCER"]) > 0
    assert len(parsed.components_by_block["DCSC"]) > 0
    assert parsed.component_classes["DCER"].__name__ == "StaticVARCompensator"
    assert parsed.component_classes["DCSC"].__name__ == "ControllableSeriesCompensator"
    assert issubclass(parsed.component_classes["DCTR"], TapTransformerControl)


def test_parse_anarede_derives_tap_changers_from_dlin() -> None:
    parsed = parse_anarede_system(DATA_DIR / "d_33nodes.pwf")

    dlin_records = parsed.components_by_block["DLIN"]
    expected_tap_count = sum(
        1 for rec in dlin_records if getattr(rec, "tap", None) not in (None, 1, 1.0)
    )

    assert expected_tap_count > 0
    assert "DLIN_TAP" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_TAP"]) == expected_tap_count
    assert issubclass(parsed.component_classes["DLIN_TAP"], TapChangingTransformer)


def test_parse_anarede_derives_phase_shifter_from_dlin_angle(tmp_path: Path) -> None:
    pwf = tmp_path / "phase_shifter_case.pwf"

    line = [" "] * 80
    line[0:5] = list("    1")
    line[10:15] = list("    2")
    line[53:58] = list("  250")
    dlin_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "Phase Test",
                "99999",
                "DLIN",
                dlin_line,
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="phase-demo")

    assert "DLIN_PHASE_SHIFT" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_PHASE_SHIFT"]) == 1
    assert issubclass(parsed.component_classes["DLIN_PHASE_SHIFT"], PhaseShiftingTransformer)


def test_parse_anarede_handles_dbsh_bank_section(tmp_path: Path) -> None:
    pwf = tmp_path / "mini_dbsh.pwf"
    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "Demo Case",
                "99999",
                "DOPC",
                "QLIM L NEWT L",
                "99999",
                "DCTE",
                "BASE 100. TEPA 1.",
                "99999",
                "DBSH",
                "    1",
                "  1  A L   1   1    10.0",
                "FBAN",
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="mini")

    assert parsed.system.name == "mini"
    assert parsed.system.description == "Demo Case"
    assert "DOPC" in parsed.components_by_block
    assert "DCTE" in parsed.components_by_block
    assert "DBSH" in parsed.components_by_block
    assert "DBSH_BANK" in parsed.components_by_block
    assert "TITU" not in parsed.components_by_block
    assert issubclass(parsed.component_classes["DBSH"], BusShunt)
    assert issubclass(parsed.component_classes["DBSH_BANK"], LineShunt)


def test_parse_pair_records_ignores_short_line() -> None:
    parser = AnaredeInfrasysParser()
    empty = parser._parse_pair_records("DOPC", "ONLYONE", {"DOPC": []})
    assert empty == []


def test_section_header_recognizes_dtpf_circ() -> None:
    parser = AnaredeInfrasysParser()
    assert parser._section_header_name("DTPF CIRC") == "DTPF_CIRC"


def test_repair_dbar_values_from_compact_voltage_angle() -> None:
    parser = AnaredeInfrasysParser()
    field_specs = {
        "voltage_limit_group": {"default": "A"},
    }
    values = {"voltage": "bad", "angle": 0.0}
    line = " " * 22 + "1000+1.2" + " " * 20

    repaired = parser._repair_dbar_values(line, field_specs, values)

    assert repaired["voltage"] == 1.0
    assert repaired["angle"] == 1.2
    assert repaired["voltage_limit_group"] == "A"


def test_parse_breaks_when_fim_inside_active_section(tmp_path: Path) -> None:
    pwf = tmp_path / "fim_break.pwf"
    pwf.write_text(
        "\n".join(
            [
                "",
                "DOPC",
                "",
                "QLIM L",
                "FIM",
                "99999",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf)
    assert len(parsed.components_by_block["DOPC"]) == 1
