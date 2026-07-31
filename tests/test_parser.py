from __future__ import annotations

from pathlib import Path

import pytest
from infrasys import System

from o_grid.models import (
    ACBus,
    ACBusTypes,
    ACLine,
    Arc,
    Area,
    AreaInterchange,
    BusShunt,
    LineShunt,
    MinMax,
    PhaseShiftingTransformer,
    TapChangingTransformer,
    TapTransformerControl,
    VoltageBaseGroup,
    VoltageLimitGroup,
)
from o_grid.parser import AnaredeInfrasysParser, parse_anarede_system, parse_rows
from o_grid.units import ActivePower, Angle, Percentage, PerUnit, ReactivePower, Voltage


def test_parser_attach_bus_areas_and_build_arc() -> None:
    parser = AnaredeInfrasysParser()
    system = System(name="demo")
    bus = ACBus(number=1, name="Bus-1", area=1)
    bus_with_text_area = ACBus(number=2, name="Bus-2", area="North")

    parser._attach_bus_areas(system, {"DBAR": [bus, bus_with_text_area]})

    assert len(list(system.get_components(Area))) == 2
    assert len(list(system.get_components(ACBus))) == 2
    assert isinstance(bus.area, Area)
    assert isinstance(bus_with_text_area.area, Area)
    assert bus_with_text_area.area.area_number is None

    line = ACLine(name="Line-1", from_bus=1, to_bus=2)
    arc = parser._build_arc_from_dlin_record(line, 3)
    assert arc.name == "Arc_3"
    assert arc.from_to == 1
    assert arc.to_from == 2


def test_parse_anarede_d9nodes_to_infrasys(data_folder: Path) -> None:
    parser = AnaredeInfrasysParser()
    parsed = parser.parse(data_folder / "anarede" / "d_9nodes.pwf")

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
    arcs = list(parsed.system.get_components(Arc))
    assert all(isinstance(arc.from_to, ACBus) for arc in arcs)
    assert all(isinstance(arc.to_from, ACBus) for arc in arcs)
    assert parsed.component_classes["DARE"].__name__ == "AreaInterchange"

    assert len(list(parsed.system.get_components(parsed.component_classes["DGBT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DGLT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DLIN_TAP"]))) == 0

    buses = parsed.components_by_block["DBAR"]
    assert all(isinstance(bus, ACBus) for bus in buses)
    assert buses[1].name == "BAR-2_GER2_2"
    assert buses[1].bustype == ACBusTypes.PV
    assert buses[0].bustype == ACBusTypes.REF
    assert buses[2].bustype == ACBusTypes.PQ
    assert all(getattr(component, "uuid", None) is not None for component in buses)
    assert all(isinstance(bus.voltage_base_group, VoltageBaseGroup) for bus in buses)
    assert all(isinstance(bus.voltage_limit_group, VoltageLimitGroup) for bus in buses)
    assert all(isinstance(bus.base_voltage, Voltage) for bus in buses)
    assert all(repr(bus.base_voltage).endswith("'kV')>") for bus in buses)
    assert all(isinstance(bus.initial_voltage, PerUnit) for bus in buses)
    assert all(isinstance(bus.angle, Angle) for bus in buses)
    assert all(isinstance(bus.voltage_limits, MinMax) for bus in buses)

    area = buses[0].area
    assert isinstance(area, Area)
    expected_peak_active_power = sum(
        float(bus.active_generation.magnitude) if bus.active_generation is not None else 0.0
        for bus in buses
    )
    expected_peak_reactive_power = sum(
        float(bus.reactive_generation.magnitude) if bus.reactive_generation is not None else 0.0
        for bus in buses
    )
    assert isinstance(area.peak_active_power, ActivePower)
    assert isinstance(area.peak_reactive_power, ReactivePower)
    assert area.peak_active_power.to("MW").magnitude == pytest.approx(expected_peak_active_power)
    assert area.peak_reactive_power.to("MVAr").magnitude == pytest.approx(
        expected_peak_reactive_power
    )

    interchange = parsed.components_by_block["DARE"][0]
    assert isinstance(interchange, AreaInterchange)
    assert isinstance(interchange.net_interchange, ActivePower)
    assert isinstance(interchange.minimum_net_interchange, ActivePower)
    assert isinstance(interchange.maximum_net_interchange, ActivePower)

    line = parsed.components_by_block["DLIN"][0]
    assert not line.name.startswith("ACLine_")
    assert getattr(line, "uuid", None) is not None
    assert isinstance(line.from_bus, ACBus)
    assert isinstance(line.to_bus, ACBus)

    assert "TITU" not in parsed.components_by_block
    assert parsed.system.description == "Sistema-Teste de 9 Barras - Caso Inicial"


def test_parse_anarede_dcer_dcsc_blocks(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes_dcer_dcsc.pwf")

    assert len(parsed.components_by_block["DCER"]) > 0
    assert len(parsed.components_by_block["DCSC"]) > 0
    assert parsed.component_classes["DCER"].__name__ == "StaticVARCompensator"
    assert parsed.component_classes["DCSC"].__name__ == "ControllableSeriesCompensator"
    assert issubclass(parsed.component_classes["DCTR"], TapTransformerControl)

    csc = parsed.components_by_block["DCSC"][0]
    assert hasattr(csc, "available")
    assert isinstance(csc.available, bool)
    assert not hasattr(csc, "operation")
    assert not hasattr(csc, "state")
    assert isinstance(csc.owner, Area)
    assert isinstance(csc.from_bus, ACBus)
    assert isinstance(csc.to_bus, ACBus)
    assert csc.to_bus.number == 848
    assert isinstance(csc.specified_value, Percentage)
    assert csc.specified_value.magnitude == -0.876
    to_bus_area = getattr(csc.to_bus, "area", None)
    assert isinstance(to_bus_area, Area)
    assert csc.owner == to_bus_area


def test_parse_anarede_derives_tap_changers_from_dlin(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes.pwf")

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


def test_parser_helper_methods_cover_core_branches() -> None:
    parser = AnaredeInfrasysParser()

    assert parser._model_field_name("type") == "bustype"
    assert parser._model_field_name("name") == "anarede_name"
    assert parser._model_field_name("voltage") == "voltage"

    class DummyGroup:
        def __init__(self, group: str) -> None:
            self.group = group

    assert parser._normalize_group_key(2.0) == "2"
    assert parser._normalize_group_key(Area(name="Area_7", area_number=7)) == "7"
    assert parser._normalize_group_key(DummyGroup("ignored")) == "IGNORED"

    name = parser._component_name("DBAR", 3, {"number": 11})
    assert name == "11_3"


def test_parse_pair_records_handles_numeric_conversion() -> None:
    parser = AnaredeInfrasysParser()
    records = parser._parse_pair_records(
        "DCTE",
        "BASE 100. TEPA 1.",
        {"DCTE": []},
    )

    assert len(records) == 2
    assert getattr(records[0], "mnemonic") == "BASE"
    assert getattr(records[0], "value") == 100.0


def test_parse_rows_normalizes_data() -> None:
    rows = [{"bus": "Bus", "load_mw": 1.5, "generator_mw": 0.0, "extra": "x"}]
    parsed = parse_rows(rows)

    assert parsed == rows


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
