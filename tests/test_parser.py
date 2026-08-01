from __future__ import annotations

import json
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
    BankController,
    BankControllerControlType,
    BusShuntBank,
    BusVoltageMonitoring,
    CircuitState,
    ConverterControl,
    ConverterMode,
    ConverterStation,
    DCBus,
    DCBusType,
    DCLine,
    DCLineData,
    FlowMonitoringCircuit,
    Generator,
    GenType,
    HighVArMode,
    IndividualizedGeneratorGroup,
    IndividualizedLoad,
    LineShunt,
    MinMax,
    OptionState,
    PhaseShiftingTransformer,
    ProgramConstant,
    ShuntBank,
    SwitchDevice,
    TapChangingTransformer,
    TapTransformerControl,
    TransferFunctionCircuit,
    TransformerDevice,
    TransformerManeuverable,
    VoltageBaseGroup,
    VoltageLimitGroup,
    VoltageMonitoringCondition,
    VoltageMonitoringSelection,
)
from o_grid.parser import AnaredeInfrasysParser, parse_anarede_system, parse_rows
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Current,
    Inductance,
    Percentage,
    PerUnit,
    ReactivePower,
    Resistance,
    Voltage,
)
from o_grid.utils.utils_parser import (
    has_non_default_tap,
    has_non_zero_angle,
    has_tap_range,
    has_tap_value,
    is_switch_impedance,
)


def test_tap_and_angle_helpers_handle_edge_values() -> None:
    assert has_non_default_tap("   ") is False
    assert has_non_default_tap(object()) is False
    assert has_non_zero_angle("   ") is False
    assert has_non_zero_angle(object()) is False


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
    parsed = parser.parse(data_folder / "pwf" / "d_9nodes.pwf")

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
    assert len(list(parsed.system.get_components(ac_line_type))) == 8
    assert len(list(parsed.system.get_components(Area))) == 1
    assert len(list(parsed.system.get_components(Arc))) == 10
    arcs = list(parsed.system.get_components(Arc))
    assert all(isinstance(arc.from_to, ACBus) for arc in arcs)
    assert all(isinstance(arc.to_from, ACBus) for arc in arcs)
    assert parsed.component_classes["DARE"].__name__ == "AreaInterchange"

    assert len(list(parsed.system.get_components(parsed.component_classes["DGBT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DGLT"]))) == 0
    assert len(list(parsed.system.get_components(parsed.component_classes["DLIN_TAP"]))) == 0
    assert (
        len(list(parsed.system.get_components(parsed.component_classes["DLIN_TRANSFORMER"]))) == 2
    )

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
    assert isinstance(interchange.area, Area)
    assert not hasattr(interchange, "area_number")
    assert not hasattr(interchange, "anarede_name")
    assert "area_token" not in interchange.ext

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
    parsed = parse_anarede_system(data_folder / "pwf" / "d_33nodes_dcer_dcsc.pwf")

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
    parsed = parse_anarede_system(data_folder / "pwf" / "d_33nodes.pwf")

    dlin_records = parsed.components_by_block["DLIN"]
    expected_tap_count = sum(
        1
        for rec in dlin_records
        if has_tap_range(
            getattr(rec, "ext", {}).get("pwf_values", {}).get("tap_minimum"),
            getattr(rec, "ext", {}).get("pwf_values", {}).get("tap_maximum"),
        )
    )
    expected_transformer_count = sum(
        1
        for rec in dlin_records
        if not has_tap_range(
            getattr(rec, "ext", {}).get("pwf_values", {}).get("tap_minimum"),
            getattr(rec, "ext", {}).get("pwf_values", {}).get("tap_maximum"),
        )
        and not has_non_zero_angle(getattr(rec, "ext", {}).get("pwf_values", {}).get("phase_shift"))
        and has_tap_value(getattr(rec, "ext", {}).get("pwf_values", {}).get("tap"))
    )

    assert expected_tap_count > 0
    assert "DLIN_TAP" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_TAP"]) == expected_tap_count
    assert issubclass(parsed.component_classes["DLIN_TAP"], TapChangingTransformer)

    assert expected_transformer_count > 0
    assert "DLIN_TRANSFORMER" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_TRANSFORMER"]) == expected_transformer_count
    assert issubclass(parsed.component_classes["DLIN_TRANSFORMER"], TransformerDevice)

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


def test_parse_anarede_derives_switch_from_zero_impedance(tmp_path: Path) -> None:
    pwf = tmp_path / "switch_case.pwf"

    line = [" "] * 80
    line[0:5] = list("    1")
    line[10:15] = list("    2")
    dlin_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "Switch Test",
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

    parsed = parse_anarede_system(pwf, system_name="switch-demo")

    assert "DLIN_SWITCH" in parsed.components_by_block
    assert len(parsed.components_by_block["DLIN_SWITCH"]) == 1
    assert issubclass(parsed.component_classes["DLIN_SWITCH"], SwitchDevice)
    switch = parsed.components_by_block["DLIN_SWITCH"][0]
    assert not hasattr(switch, "tap")


def test_switch_impedance_helpers() -> None:
    assert has_tap_value("1.") is True
    assert has_tap_value("   ") is False
    assert has_tap_value(None) is False
    assert has_tap_value(1.0) is True
    assert has_tap_range("", "1.10") is True
    assert has_tap_range("", "") is False
    assert is_switch_impedance(0.0, 0.0, 0.0, 0.001) is True
    assert is_switch_impedance(0.0005, 0.0005, 0.0005, 0.001) is True
    assert is_switch_impedance(0.0, 0.001, 0.958, 0.001) is False
    assert is_switch_impedance("0.0", "0.0", "0.0", 0.001) is True


def test_parse_anarede_derives_maneuverable_flag_on_transformer(tmp_path: Path) -> None:
    pwf = tmp_path / "maneuverable_case.pwf"

    line = [" "] * 80
    line[0:5] = list("    1")
    line[10:15] = list("    2")
    line[19] = "N"
    line[38:43] = list("01050")
    dlin_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "Maneuverable Test",
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

    parsed = parse_anarede_system(pwf, system_name="maneuverable-demo")

    assert "DLIN_TRANSFORMER" in parsed.components_by_block
    tap_transformer = parsed.components_by_block["DLIN_TRANSFORMER"][0]
    assert tap_transformer.maneuverable is TransformerManeuverable.NON_MANEUVERABLE

    base_line = parsed.components_by_block["DLIN"][0]
    assert not hasattr(base_line, "maneuverable")

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


def test_derived_transformers_use_availability_and_drop_operation() -> None:
    tap = TapChangingTransformer(name="tap", from_bus=1, to_bus=2, available=True)
    phase = PhaseShiftingTransformer(name="phase", from_bus=1, to_bus=2, available=False)

    assert tap.available is True
    assert phase.available is False
    assert not hasattr(tap, "state")
    assert not hasattr(phase, "state")
    assert not hasattr(tap, "operation")
    assert not hasattr(phase, "operation")


def test_attach_ctap_options_flags_selected_circuits() -> None:
    parser = AnaredeInfrasysParser()
    circuit = TransferFunctionCircuit(
        name="dtpf",
        from_bus_1=776,
        to_bus_1=2971,
        circuit_1=2,
        from_bus_2=1320,
        to_bus_2=1368,
        circuit_2=1,
    )

    from_bus = ACBus(number=776, name="A")
    to_bus = ACBus(number=2971, name="B")
    matched_line = ACLine(name="line", line_circuit=2)
    object.__setattr__(matched_line, "from_bus", from_bus)
    object.__setattr__(matched_line, "to_bus", to_bus)

    # Reversed orientation using unresolved raw bus numbers.
    reversed_tap = TapChangingTransformer(name="tap", from_bus=1368, to_bus=1320, line_circuit=1)
    unmatched = PhaseShiftingTransformer(name="phase", from_bus=1, to_bus=2, line_circuit=9)

    parser._attach_ctap_options(
        {
            "DTPF_CIRC": [circuit],
            "DLIN": [matched_line],
            "DLIN_TAP": [reversed_tap],
            "DLIN_PHASE_SHIFT": [unmatched],
        }
    )

    assert matched_line.ctap_option is True
    assert reversed_tap.ctap_option is True
    assert unmatched.ctap_option is False


def test_attach_flow_monitoring_flags_selected_circuits() -> None:
    parser = AnaredeInfrasysParser()
    circuit = FlowMonitoringCircuit(
        name="dmfl",
        from_bus_1=776,
        to_bus_1=2971,
        circuit_1=2,
        from_bus_2=1320,
        to_bus_2=1368,
        circuit_2=1,
    )

    from_bus = ACBus(number=776, name="A")
    to_bus = ACBus(number=2971, name="B")
    matched_line = ACLine(name="line", line_circuit=2)
    object.__setattr__(matched_line, "from_bus", from_bus)
    object.__setattr__(matched_line, "to_bus", to_bus)

    # Reversed orientation using unresolved raw bus numbers.
    reversed_tap = TapChangingTransformer(name="tap", from_bus=1368, to_bus=1320, line_circuit=1)
    unmatched = PhaseShiftingTransformer(name="phase", from_bus=1, to_bus=2, line_circuit=9)

    parser._attach_flow_monitoring(
        {
            "DMFL_CIRC": [circuit],
            "DLIN": [matched_line],
            "DLIN_TAP": [reversed_tap],
            "DLIN_PHASE_SHIFT": [unmatched],
        }
    )

    assert matched_line.flow_monitoring is True
    assert reversed_tap.flow_monitoring is True
    assert unmatched.flow_monitoring is False


def test_attach_bus_voltage_monitoring_builds_sets() -> None:
    parser = AnaredeInfrasysParser()
    system = System(name="dmte")

    area = Area(name="Area_2", area_number=2)
    bus_with_area = ACBus(number=813, name="B813")
    object.__setattr__(bus_with_area, "area", area)
    other_bus = ACBus(number=822, name="B822")
    existing_group = VoltageBaseGroup(name="DGBT_1", voltage=Voltage(345, "kV"))

    selection = VoltageMonitoringSelection(
        name="dmte1",
        element_type_1="BARR",
        element_id_1=813,
        condition_1="A",
        element_type_2="AREA",
        element_id_2=2,
        main_condition="E",
        element_type_3="TENS",
        element_id_3=345,
        condition_2="A",
        element_type_4="TENS",
        element_id_4=500,
    )
    unresolved = VoltageMonitoringSelection(
        name="dmte2",
        element_type_1="AG01",
        element_id_1=1,
    )

    parser._attach_bus_voltage_monitoring(
        system,
        {
            "DMTE": [selection, unresolved],
            "DBAR": [bus_with_area, other_bus],
            "DGBT": [existing_group],
        },
    )

    monitorings = list(system.get_components(BusVoltageMonitoring))
    assert len(monitorings) == 1

    monitoring = monitorings[0]
    assert [type(element).__name__ for element in monitoring.type] == [
        "ACBus",
        "Area",
        "VoltageBaseGroup",
        "VoltageBaseGroup",
    ]
    assert monitoring.type[0].number == 813
    assert monitoring.type[1].area_number == 2
    assert monitoring.type[2] is existing_group
    assert monitoring.type[3].voltage == Voltage(500, "kV")
    assert monitoring.condition == [
        VoltageMonitoringCondition.INTERVAL,
        VoltageMonitoringCondition.UNION,
        VoltageMonitoringCondition.INTERVAL,
        None,
    ]


def test_components_store_pwf_values(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "pwf" / "d_9nodes.pwf")

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
    parsed = parse_anarede_system(data_folder / "pwf" / "d_33nodes_dcer_dcsc.pwf")

    constant = parsed.components_by_block["DCTE"][0]

    assert isinstance(constant, ProgramConstant)
    assert not hasattr(constant, "available")
    assert not hasattr(constant, "category")
    assert not hasattr(constant, "ext")


def test_parse_anarede_csc_measurement_terminal_is_bus(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "pwf" / "d_33nodes_dcer_dcsc.pwf")

    csc = parsed.components_by_block["DCSC"][0]
    assert isinstance(csc.measurement_terminal, ACBus)


def test_parse_anarede_svc_controlled_bus_is_bus(data_folder: Path) -> None:
    parsed = parse_anarede_system(data_folder / "pwf" / "d_33nodes_dcer_dcsc.pwf")

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
    assert issubclass(parsed.component_classes["DBSH"], BankController)
    assert issubclass(parsed.component_classes["DBSH_BANK"], ShuntBank)

    # The controller is embedded in the bank, not registered as a top-level component.
    assert not list(parsed.system.get_components(BankController))
    banks = list(parsed.system.get_components(ShuntBank))
    assert len(banks) == 1
    bank = banks[0]
    assert isinstance(bank, BusShuntBank)
    assert isinstance(bank.bank_controller, BankController)
    assert bank.bank_controller.control_type is BankControllerControlType.VOLTAGE_CONTROL_RANGE
    assert not hasattr(bank, "operation")
    assert not hasattr(bank, "state")
    assert bank.available is True
    assert isinstance(bank.reactive_power_per_unit, ReactivePower)
    assert bank.reactive_power_per_unit.to("MVAr").magnitude == 10.0


def test_parse_pair_records_ignores_short_line() -> None:
    parser = AnaredeInfrasysParser()
    empty = parser._parse_pair_records("DOPC", "ONLYONE", {"DOPC": []})
    assert empty == []


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


def test_section_header_recognizes_dmfl_circ() -> None:
    parser = AnaredeInfrasysParser()
    assert parser._section_header_name("DMFL CIRC") == "DMFL_CIRC"


def test_section_header_recognizes_dmte() -> None:
    parser = AnaredeInfrasysParser()
    assert parser._section_header_name("DMTE") == "DMTE"


def test_delo_resolves_power_base_from_dase_and_units(tmp_path: Path) -> None:
    def delo_line(number: int, power_base_text: str) -> str:
        chars = [" "] * 80
        chars[0:4] = list(f"{number:>4}")
        chars[7:12] = list("  600")
        chars[13:18] = list(power_base_text.rjust(5))
        chars[19:39] = list("ELO TESTE".ljust(20))
        chars[40] = "N"
        chars[42] = "L"
        return "".join(chars)

    pwf = tmp_path / "delo_case.pwf"
    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "DELO Test",
                "99999",
                "DCTE",
                "DASE 1500.",
                "99999",
                "DELO",
                delo_line(1, ""),
                delo_line(2, "800"),
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="delo-demo")
    links = parsed.components_by_block["DELO"]
    assert len(links) == 2

    first, second = links
    assert isinstance(first, DCLineData)
    assert first.himvar_mode is HighVArMode.NORMAL_MODE
    assert first.state is CircuitState.CLOSED
    assert isinstance(first.voltage, Voltage)
    assert first.voltage.to("kV").magnitude == 600.0
    assert not hasattr(first, "operation")

    # Blank power base falls back to the DASE program constant.
    assert isinstance(first.power_base, ActivePower)
    assert first.power_base.to("MW").magnitude == 1500.0

    # Explicit power base is preserved.
    assert isinstance(second.power_base, ActivePower)
    assert second.power_base.to("MW").magnitude == 800.0


def test_delo_power_base_defaults_to_dase_constant(tmp_path: Path) -> None:
    def delo_line(number: int) -> str:
        chars = [" "] * 80
        chars[0:4] = list(f"{number:>4}")
        chars[7:12] = list("  500")
        chars[19:39] = list("ELO SEM DASE".ljust(20))
        chars[40] = "N"
        chars[42] = "L"
        return "".join(chars)

    pwf = tmp_path / "delo_no_dase.pwf"
    pwf.write_text(
        "\n".join(
            [
                "DELO",
                delo_line(1),
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="delo-default")
    link = parsed.components_by_block["DELO"][0]

    # ANAREDE default DC system power base when DASE is not declared.
    assert isinstance(link.power_base, ActivePower)
    assert link.power_base.to("MW").magnitude == 100.0


def test_embed_dc_line_data_matches_link_by_number() -> None:
    parser = AnaredeInfrasysParser()
    from_bus = DCBus(number=1, name="DC-1", dc_link_number=2)
    to_bus = DCBus(number=2, name="DC-2", dc_link_number=2)
    line = DCLine(name="DC-1_DC-2", from_bus=from_bus, to_bus=to_bus)
    link = DCLineData(name="link-2", number=2)
    other = DCLineData(name="link-9", number=9)

    parser._embed_dc_line_data({"DCLI": [line], "DELO": [link, other]})

    assert isinstance(line.line_data, DCLineData)
    assert line.line_data is link


def test_dshl_shunt_units_and_circuit_state(tmp_path: Path) -> None:
    def dshl_line(
        from_bus: int,
        to_bus: int,
        shunt_from: str,
        shunt_to: str,
        state_from: str,
        state_to: str,
    ) -> str:
        chars = [" "] * 80
        chars[0:5] = list(f"{from_bus:>5}")
        chars[9:14] = list(f"{to_bus:>5}")
        chars[14:16] = list(" 1")
        chars[17:23] = list(shunt_from.rjust(6))
        chars[23:29] = list(shunt_to.rjust(6))
        chars[30:32] = list(state_from.rjust(2))
        chars[33:35] = list(state_to.rjust(2))
        return "".join(chars)

    pwf = tmp_path / "dshl_case.pwf"
    pwf.write_text(
        "\n".join(
            [
                "DSHL",
                dshl_line(101, 102, "-73.0", "0.0", "L", "D"),
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dshl-demo")
    shunts = parsed.components_by_block["DSHL"]
    assert len(shunts) == 1

    shunt = shunts[0]
    assert isinstance(shunt, LineShunt)
    assert not hasattr(shunt, "operation")

    assert isinstance(shunt.shunt_from, ReactivePower)
    assert shunt.shunt_from.to("MVAr").magnitude == -73.0
    assert isinstance(shunt.shunt_to, ReactivePower)
    assert shunt.shunt_to.to("MVAr").magnitude == 0.0
    assert shunt.state_from is CircuitState.CLOSED
    assert shunt.state_to is CircuitState.OPEN


def test_attach_generator_active_power_from_dbar() -> None:
    parser = AnaredeInfrasysParser()
    generator = Generator(name="G1", number=11)
    other = Generator(name="G2", number=99)
    bus = ACBus(number=11, name="Bus-11", active_generation=ActivePower(1350.0, "MW"))

    parser._attach_generator_active_power({"DGER": [generator, other], "DBAR": [bus]})

    assert isinstance(generator.active_generation, ActivePower)
    assert generator.active_generation.to("MW").magnitude == 1350.0
    # Generators without a matching bus keep their default.
    assert other.active_generation is None
    assert not hasattr(generator, "operation")


def test_attach_generator_types_by_bus_number() -> None:
    parser = AnaredeInfrasysParser()
    parser._gen_type_by_bus = {"10": GenType.NUCLEAR, "12": GenType.HYDRO}
    nuclear = Generator(name="G1", number=10)
    hydro = Generator(name="G2", number=12)
    unmatched = Generator(name="G3", number=99)

    parser._attach_generator_types({"DGER": [nuclear, hydro, unmatched]})

    assert nuclear.gen_type is GenType.NUCLEAR
    assert hydro.gen_type is GenType.HYDRO
    assert unmatched.gen_type is None


def test_load_gen_type_mapping_indexes_by_bus_number(tmp_path: Path) -> None:
    mapping_file = tmp_path / "gen_type_mapping.json"
    mapping_file.write_text(
        json.dumps(
            {
                "10ANGRA1UNE001": {
                    "number": 10,
                    "bus_name": "ANGRA1UNE001",
                    "area": 44,
                    "type": "Nuclear",
                },
                "12LCBARRUHE005": {
                    "number": 12,
                    "bus_name": "LCBARRUHE005",
                    "area": 1,
                    "type": "Hydro",
                },
            }
        ),
        encoding="utf-8",
    )

    index = AnaredeInfrasysParser._load_gen_type_mapping(mapping_file)

    assert index == {"10": GenType.NUCLEAR, "12": GenType.HYDRO}
    assert AnaredeInfrasysParser._load_gen_type_mapping(tmp_path / "missing.json") == {}


def test_attach_generator_number_resolves_to_bus() -> None:
    parser = AnaredeInfrasysParser()
    generator = Generator(name="G1", number=11)
    other = Generator(name="G2", number=99)
    bus = ACBus(number=11, name="Bus-11")

    parser._attach_component_bus_references({"DGER": [generator, other], "DBAR": [bus]})

    assert generator.number is bus
    # Generators without a matching bus keep their raw number.
    assert other.number == 99


def test_dcai_individualized_load_units_and_availability(tmp_path: Path) -> None:
    def dcai_line(bus: int, state: str, active: str, reactive: str) -> str:
        chars = [" "] * 80
        chars[0:5] = list(f"{bus:>5}")
        chars[9:11] = list(" 9")
        chars[12] = state
        chars[14:17] = list("  1")
        chars[18:21] = list("  1")
        chars[22:27] = list(active.rjust(5))
        chars[28:33] = list(reactive.rjust(5))
        chars[50:55] = list(" 80.0")
        chars[56:60] = list("1015")
        return "".join(chars)

    pwf = tmp_path / "dcai_case.pwf"
    pwf.write_text(
        "\n".join(
            [
                "DCAI",
                dcai_line(87, "L", "132.5", "73.29"),
                dcai_line(88, "D", "10.0", "5.0"),
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dcai-demo")
    loads = parsed.components_by_block["DCAI"]
    assert len(loads) == 2

    first, second = loads
    assert isinstance(first, IndividualizedLoad)

    # operation and state are folded into the availability flag.
    assert not hasattr(first, "operation")
    assert not hasattr(first, "state")
    assert first.available is True
    assert second.available is False

    assert isinstance(first.active_power, ActivePower)
    assert first.active_power.to("MW").magnitude == 132.5
    assert isinstance(first.reactive_power, ReactivePower)
    assert first.reactive_power.to("MVAr").magnitude == 73.29
    assert isinstance(first.parameter_a, Percentage)
    assert isinstance(first.voltage_limit, Percentage)
    assert first.voltage_limit.to("percent").magnitude == 80.0
    assert isinstance(first.voltage_for_load_definition, PerUnit)
    assert first.voltage_for_load_definition.to("pu").magnitude == 1.015


def test_attach_individualized_load_bus_reference() -> None:
    parser = AnaredeInfrasysParser()
    load = IndividualizedLoad(name="87_9", bus=87)
    other = IndividualizedLoad(name="99_1", bus=99)
    bus = ACBus(number=87, name="Bus-87")

    parser._attach_component_bus_references({"DCAI": [load, other], "DBAR": [bus]})

    assert isinstance(load.bus, ACBus)
    assert load.bus is bus
    # Loads without a matching bus keep the raw number.
    assert other.bus == 99


def test_attach_individualized_generator_group_bus_reference() -> None:
    parser = AnaredeInfrasysParser()
    group = IndividualizedGeneratorGroup(name="5103_20", bus=5103)
    other = IndividualizedGeneratorGroup(name="9999_1", bus=9999)
    bus = ACBus(number=5103, name="Bus-5103")

    parser._attach_component_bus_references({"DGEI": [group, other], "DBAR": [bus]})

    assert isinstance(group.bus, ACBus)
    assert group.bus is bus
    # Groups without a matching bus keep the raw number.
    assert other.bus == 9999


def test_attach_bank_controller_extremity_bus_reference() -> None:
    parser = AnaredeInfrasysParser()
    controller = BankController(name="100_74", from_bus=100, to_bus=4598, extremity_bus=100)
    bus = ACBus(number=100, name="Bus-100")

    parser._attach_component_bus_references({"DBSH": [controller], "DBAR": [bus]})

    assert isinstance(controller.extremity_bus, ACBus)
    assert controller.extremity_bus is bus


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


def test_parse_dcba_type_stays_on_dc_bus(tmp_path: Path) -> None:
    pwf = tmp_path / "mini_dcba.pwf"

    line = [" "] * 80
    line[0:4] = list("   1")
    line[5] = "A"
    line[7] = "1"
    line[8] = "+"
    line[9:21] = list("DCBUS-1     ")
    line[21:23] = list("01")
    line[23:28] = list("50000")
    line[71:75] = list("   1")
    dcba_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "DC Case",
                "99999",
                "DCBA",
                dcba_line,
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dc-demo")

    assert "DCBA" in parsed.components_by_block
    assert len(parsed.components_by_block["DCBA"]) == 1
    dc_bus = parsed.components_by_block["DCBA"][0]
    assert isinstance(dc_bus, DCBus)
    assert dc_bus.type == DCBusType.REFERENCE
    assert isinstance(dc_bus.voltage, Voltage)
    assert dc_bus.voltage.to("kV").magnitude == pytest.approx(50000.0)
    assert dc_bus.ground_electrode_resistance is None
    assert not hasattr(dc_bus, "anarede_name")
    assert not hasattr(dc_bus, "operation")
    assert not hasattr(dc_bus, "bustype")
    assert not hasattr(dc_bus, "area")
    assert not hasattr(dc_bus, "voltage_limits")
    assert not hasattr(dc_bus, "base_voltage")
    assert not hasattr(dc_bus, "voltage_limit_group")


def test_parse_dccv_drops_operation_field(tmp_path: Path) -> None:
    pwf = tmp_path / "mini_dccv.pwf"

    line = [" "] * 80
    line[0:4] = list("   2")
    line[5] = "A"
    line[7] = "F"
    line[9] = "P"
    line[11:16] = list("10180")
    dccv_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "DCCV Case",
                "99999",
                "DCCV",
                dccv_line,
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dccv-demo")

    assert "DCCV" in parsed.components_by_block
    assert len(parsed.components_by_block["DCCV"]) == 1
    control = parsed.components_by_block["DCCV"][0]
    assert isinstance(control, ConverterControl)
    assert not hasattr(control, "operation")


def test_parse_dcnv_drops_operation_and_applies_units(tmp_path: Path) -> None:
    pwf = tmp_path / "mini_dcnv.pwf"

    line = [" "] * 80
    line[0:4] = list("   2")
    line[5] = "A"
    line[7:12] = list("   86")
    line[13:17] = list("  20")
    line[18:22] = list("  40")
    line[23] = "I"
    line[25] = "4"
    line[27:32] = list(" 2610")
    line[33:38] = list(" 17.2")
    line[39:44] = list("  122")
    line[45:50] = list("  450")
    line[57:62] = list("  0.0")
    line[63:68] = list("  0.0")
    line[69:71] = list("60")
    dcnv_line = "".join(line)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "DCNV Case",
                "99999",
                "DCNV",
                dcnv_line,
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dcnv-demo")

    assert "DCNV" in parsed.components_by_block
    assert len(parsed.components_by_block["DCNV"]) == 1
    converter = parsed.components_by_block["DCNV"][0]
    assert isinstance(converter, ConverterStation)
    assert not hasattr(converter, "operation")
    assert converter.mode == ConverterMode.INVERTER
    assert isinstance(converter.current, Current)
    assert converter.current.to("A").magnitude == 2610.0


def test_parser_resolves_converter_station_bus_instances() -> None:
    parser = AnaredeInfrasysParser()
    ac_bus = ACBus(number=86, name="AC_86", bustype=ACBusTypes.PQ)
    dc_bus = DCBus(number=20, name="DC_20")
    neutral_bus = DCBus(number=40, name="DC_40")
    converter = ConverterStation(
        name="conv-1",
        ac_bus=86,
        dc_bus=20,
        neutral_bus=40,
    )
    components_by_block = {
        "DBAR": [ac_bus],
        "DCBA": [dc_bus, neutral_bus],
        "DCNV": [converter],
    }

    parser._attach_component_bus_references(components_by_block)
    parser._attach_dc_bus_references(components_by_block)

    assert converter.ac_bus is ac_bus
    assert converter.dc_bus is dc_bus
    assert converter.neutral_bus is neutral_bus


def test_parse_dcli_resolves_dc_buses_and_names_by_pole(tmp_path: Path) -> None:
    pwf = tmp_path / "mini_dcli.pwf"

    def dcba(number: str, name: str, polarity: str) -> str:
        row = [" "] * 80
        row[0:4] = list(number.rjust(4))
        row[5] = "A"
        row[7] = "1"
        row[8] = polarity
        row[9:21] = list(name.ljust(12))
        return "".join(row)

    dcli = [" "] * 80
    dcli[0:4] = list("  10")
    dcli[5] = "A"
    dcli[8:12] = list("  20")
    dcli[17:23] = list(" 10.47")
    dcli[60:64] = list("9999")
    dcli_line = "".join(dcli)

    pwf.write_text(
        "\n".join(
            [
                "TITU",
                "DC Case",
                "99999",
                "DCBA",
                dcba("10", "DCFROM", "+"),
                dcba("20", "DCTO", "+"),
                "99999",
                "DCLI",
                dcli_line,
                "99999",
                "FIM",
                "",
            ]
        ),
        encoding="cp1252",
    )

    parsed = parse_anarede_system(pwf, system_name="dcli-demo")

    link = parsed.components_by_block["DCLI"][0]
    assert isinstance(link, DCLine)
    assert isinstance(link.from_bus, DCBus)
    assert isinstance(link.to_bus, DCBus)
    assert link.from_bus.number == 10
    assert link.to_bus.number == 20
    assert link.name == "DCFROM_DCTO_+"
    assert link.dcli_circuit == 1
    assert not hasattr(link, "operation")
    assert isinstance(link.resistance, Resistance)
    assert link.resistance.to("ohm").magnitude == 10.47
    assert repr(link.resistance) == "<Quantity(10.47, 'Ω')>"
    assert isinstance(link.inductance, Inductance)
    assert isinstance(link.capacity, ActivePower)
    assert link.capacity.to("MW").magnitude == 9999.0


def test_parser_assigns_dcli_circuit_defaults_by_operation() -> None:
    parser = AnaredeInfrasysParser()

    def make_link(from_bus: int, to_bus: int, circuit: int | None, operation: str) -> DCLine:
        link = DCLine(
            name=f"{from_bus}_{to_bus}",
            from_bus=from_bus,
            to_bus=to_bus,
            dcli_circuit=circuit,
        )
        link.ext["pwf_values"] = {
            "from_bus": from_bus,
            "to_bus": to_bus,
            "dcli_circuit": circuit,
            "operation": operation,
        }
        return link

    add1 = make_link(10, 20, None, "A")
    add2 = make_link(10, 20, None, "A")
    explicit = make_link(10, 20, 5, "A")
    add3 = make_link(10, 20, None, "A")
    modify = make_link(10, 20, None, "M")
    other = make_link(30, 40, None, "A")

    parser._assign_dcli_circuit_defaults({"DCLI": [add1, add2, explicit, add3, modify, other]})

    assert add1.dcli_circuit == 1
    assert add2.dcli_circuit == 2
    assert explicit.dcli_circuit == 5
    assert add3.dcli_circuit == 6
    assert modify.dcli_circuit == 1
    assert other.dcli_circuit == 1


def test_parser_dcli_bus_fields_prefer_dc_buses_over_ac_buses() -> None:
    parser = AnaredeInfrasysParser()
    ac_bus = ACBus(number=10, name="AC_10", bustype=ACBusTypes.PQ)
    dc_from = DCBus(number=10, name="DCFROM")
    dc_to = DCBus(number=20, name="DCTO")
    link = DCLine(name="link-1", from_bus=10, to_bus=20)
    components_by_block = {
        "DBAR": [ac_bus],
        "DCBA": [dc_from, dc_to],
        "DCLI": [link],
    }

    parser._attach_component_bus_references(components_by_block)
    parser._attach_dc_bus_references(components_by_block)

    assert link.from_bus is dc_from
    assert link.to_bus is dc_to
