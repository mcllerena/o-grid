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
    OptionState,
    PhaseShiftingTransformer,
    ProgramConstant,
    TapChangingTransformer,
    TapTransformerControl,
    VoltageBaseGroup,
    VoltageLimitGroup,
)
from o_grid.parser import AnaredeInfrasysParser, parse_anarede_system, parse_rows
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Percentage,
    PerUnit,
    ReactivePower,
    Voltage,
)


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
    assert line.name == f"{line.from_bus.name}_{line.to_bus.name}_{line.line_circuit}"
    assert getattr(line, "uuid", None) is not None
    assert isinstance(line.from_bus, ACBus)
    assert isinstance(line.to_bus, ACBus)
    assert isinstance(line.controlled_bus, ACBus)
    assert line.controlled_bus == line.from_bus
    assert line.line_circuit == 1
    assert isinstance(line.r, Percentage)
    assert isinstance(line.x, Percentage)
    assert isinstance(line.rating, ApparentPower)
    assert line.b is not None
    assert line.g is not None
    assert isinstance(line.g.from_to, ActivePower)
    assert isinstance(line.g.to_from, ActivePower)

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

    line = parsed.components_by_block["DLIN"][0]
    from_bus_area = getattr(line.from_bus, "area", None)
    assert isinstance(from_bus_area, Area)
    assert isinstance(line.owner, Area)
    assert line.owner == from_bus_area

    mapped_line = next(
        rec
        for rec in parsed.components_by_block["DLIN"]
        if isinstance(rec.from_bus, ACBus)
        and isinstance(rec.to_bus, ACBus)
        and rec.from_bus.number == 824
        and rec.to_bus.number == 933
        and rec.line_circuit == 2
    )
    assert isinstance(mapped_line.r, Percentage)
    assert isinstance(mapped_line.x, Percentage)
    assert isinstance(mapped_line.rating, ApparentPower)
    assert mapped_line.b is not None
    assert isinstance(mapped_line.b.from_to, ReactivePower)
    assert isinstance(mapped_line.b.to_from, ReactivePower)
    assert mapped_line.g is not None
    assert isinstance(mapped_line.g.from_to, ActivePower)
    assert isinstance(mapped_line.g.to_from, ActivePower)
    assert mapped_line.r.magnitude == pytest.approx(0.01)
    assert mapped_line.x.magnitude == pytest.approx(0.126)
    assert mapped_line.rating.magnitude == pytest.approx(2182.0)
    assert mapped_line.b.from_to.magnitude == pytest.approx(15.428)
    assert mapped_line.b.to_from.magnitude == pytest.approx(15.428)
    assert mapped_line.g.from_to.magnitude == pytest.approx(0.0)
    assert mapped_line.g.to_from.magnitude == pytest.approx(0.0)

    to_owner_line = next(
        rec
        for rec in parsed.components_by_block["DLIN"]
        if str(getattr(rec, "ext", {}).get("pwf_values", {}).get("owner", "")).strip().upper()
        == "T"
    )
    to_bus_area = getattr(to_owner_line.to_bus, "area", None)
    assert isinstance(to_bus_area, Area)
    assert to_owner_line.owner == to_bus_area

    negative_controlled_line = next(
        rec
        for rec in parsed.components_by_block["DLIN"]
        if isinstance(
            getattr(rec, "ext", {}).get("pwf_values", {}).get("controlled_bus"),
            (int, float),
        )
        and float(getattr(rec, "ext", {}).get("pwf_values", {}).get("controlled_bus")) < 0
    )
    assert isinstance(negative_controlled_line.controlled_bus, ACBus)
    assert negative_controlled_line.controlled_bus == negative_controlled_line.to_bus


def test_parse_anarede_derives_tap_changers_from_dlin(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes.pwf")

    dlin_records = parsed.components_by_block["DLIN"]
    expected_tap_count = sum(
        1
        for rec in dlin_records
        if AnaredeInfrasysParser._has_non_default_tap(
            getattr(rec, "ext", {}).get("pwf_values", {}).get("tap")
        )
    )

    assert expected_tap_count > 0
    assert "DLIN_TAP" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_TAP"]) == expected_tap_count
    assert issubclass(parsed.component_classes["DLIN_TAP"], TapChangingTransformer)

    tap_transformer = parsed.components_by_block["DLIN_TAP"][0]
    assert isinstance(tap_transformer.controlled_bus, ACBus)
    assert isinstance(tap_transformer.owner, Area)
    assert isinstance(tap_transformer.r, Percentage)
    assert isinstance(tap_transformer.x, Percentage)
    assert isinstance(tap_transformer.rating, ApparentPower)
    assert tap_transformer.b is not None
    assert isinstance(tap_transformer.b.from_to, ReactivePower)
    assert isinstance(tap_transformer.b.to_from, ReactivePower)
    assert tap_transformer.name == (
        f"{tap_transformer.from_bus.name}_{tap_transformer.to_bus.name}_{tap_transformer.line_circuit}"
    )


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


def test_rename_dlin_components_applies_to_derived_transformers() -> None:
    parser = AnaredeInfrasysParser()
    from_bus = ACBus(number=1, name="FROM")
    to_bus = ACBus(number=2, name="TO")

    tap = TapChangingTransformer(name="tap", from_bus=1, to_bus=2, line_circuit=7)
    phase = PhaseShiftingTransformer(name="phase", from_bus=1, to_bus=2, line_circuit=8)
    object.__setattr__(tap, "from_bus", from_bus)
    object.__setattr__(tap, "to_bus", to_bus)
    object.__setattr__(phase, "from_bus", from_bus)
    object.__setattr__(phase, "to_bus", to_bus)

    parser._rename_dlin_components(
        {
            "DLIN": [],
            "DLIN_TAP": [tap],
            "DLIN_PHASE_SHIFT": [phase],
        }
    )

    assert tap.name == "FROM_TO_7"
    assert phase.name == "FROM_TO_8"


def test_dlin_helper_parsers_handle_quantity_and_text_inputs() -> None:
    assert AnaredeInfrasysParser._has_non_default_tap(PerUnit(0.98, "pu"))
    assert not AnaredeInfrasysParser._has_non_default_tap("   ")
    assert AnaredeInfrasysParser._has_non_default_tap("X")

    assert AnaredeInfrasysParser._has_non_zero_angle(Angle(1.5, "degree"))
    assert not AnaredeInfrasysParser._has_non_zero_angle("X")


def test_components_store_pwf_values(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_9nodes.pwf")

    bus = parsed.components_by_block["DBAR"][0]
    line = parsed.components_by_block["DLIN"][0]
    option = parsed.components_by_block["DOPC"][0]

    assert "pwf_values" in bus.ext
    assert isinstance(bus.ext["pwf_values"], dict)

    assert "pwf_values" in line.ext
    assert isinstance(line.ext["pwf_values"], dict)

    assert option.state == OptionState.ACTIVATED
    assert not hasattr(option, "available")
    assert not hasattr(option, "category")
    assert not hasattr(option, "ext")


def test_program_constant_shape_is_minimal(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes_dcer_dcsc.pwf")

    constant = parsed.components_by_block["DCTE"][0]

    assert isinstance(constant, ProgramConstant)
    assert not hasattr(constant, "available")
    assert not hasattr(constant, "category")
    assert not hasattr(constant, "ext")


def test_parse_anarede_csc_measurement_terminal_is_bus(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes_dcer_dcsc.pwf")

    csc = parsed.components_by_block["DCSC"][0]
    assert isinstance(csc.measurement_terminal, ACBus)


def test_parse_anarede_svc_controlled_bus_is_bus(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "anarede" / "d_33nodes_dcer_dcsc.pwf")

    svc = parsed.components_by_block["DCER"][0]
    assert isinstance(svc.controlled_bus, ACBus)


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
    assert isinstance(getattr(records[0], "value"), ApparentPower)
    assert getattr(records[0], "value").magnitude == 100.0
    assert getattr(records[1], "mnemonic") == "TEPA"
    assert isinstance(getattr(records[1], "value"), ActivePower)
    assert getattr(records[1], "value").magnitude == 1.0


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
