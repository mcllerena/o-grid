from __future__ import annotations

import math

from o_grid.models import (
    ACBranch,
    ACBus,
    ACBusTypes,
    ACLine,
    Area,
    BankController,
    BankControllerControlType,
    Branch,
    BusShuntBank,
    CircuitState,
    ControllableSeriesCompensator,
    ConverterControl,
    ConverterControlSlack,
    ConverterControlType,
    ConverterMode,
    ConverterStation,
    CSCControlMode,
    DCBus,
    DCBusPolarity,
    DCBusType,
    Generator,
    InverterControlMode,
    Line,
    LineShunt,
    LineShuntBank,
    LTCTransformer,
    MinMax,
    PhaseShiftingTransformer,
    ProgramConstant,
    ShuntBank,
    ShuntControlMode,
    StaticVARCompensator,
    SVCControlMode,
    TapChangingTransformer,
    TapTransformerControl,
)
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Capacitance,
    Current,
    Frequency,
    Inductance,
    Percentage,
    PerUnit,
    ReactivePower,
    Resistance,
    Voltage,
    ureg,
)


def test_models_package_exports_expected_types() -> None:
    assert ACBus.__name__ == "ACBus"
    assert ACLine.__name__ == "ACLine"
    assert Branch.__name__ == "Branch"
    assert ACBranch.__name__ == "ACBranch"
    assert Line.__name__ == "Line"
    assert Generator.__name__ == "Generator"
    assert BankController.__name__ == "BankController"
    assert BusShuntBank.__name__ == "BusShuntBank"
    assert LineShuntBank.__name__ == "LineShuntBank"
    assert ShuntBank.__name__ == "ShuntBank"
    assert LineShunt.__name__ == "LineShunt"
    assert TapChangingTransformer.__name__ == "LTCTransformer"
    assert LTCTransformer.__name__ == "LTCTransformer"
    assert PhaseShiftingTransformer.__name__ == "PhaseShiftingTransformer"
    assert StaticVARCompensator.__name__ == "StaticVARCompensator"
    assert ControllableSeriesCompensator.__name__ == "ControllableSeriesCompensator"
    assert TapTransformerControl.__name__ == "TapTransformerControl"


def test_acline_follows_branch_hierarchy() -> None:
    assert issubclass(ACLine, Line)
    assert issubclass(Line, ACBranch)
    assert issubclass(ACBranch, Branch)


def test_example_helpers_expose_public_class_types() -> None:
    assert isinstance(Branch.example(), Branch)
    assert isinstance(Line.example(), Line)
    assert isinstance(ACBus.example(), ACBus)
    assert isinstance(Area.example(), Area)


def test_acbus_example_uses_r2x_style_fields() -> None:
    bus = ACBus.example()

    assert bus.bustype == ACBusTypes.PV
    assert isinstance(bus.base_voltage, Voltage)
    assert bus.base_voltage.magnitude == 138.0
    assert repr(bus.base_voltage) == "<Quantity(138.0, 'kV')>"
    assert bus.voltage_limits == MinMax(min=0.9, max=1.1)
    assert isinstance(bus.initial_voltage, PerUnit)
    assert isinstance(bus.angle, Angle)
    assert isinstance(bus.voltage_for_load_definition, PerUnit)
    assert isinstance(bus.active_generation, ActivePower)
    assert bus.active_generation.magnitude == 1000.0
    assert isinstance(bus.reactive_generation, ReactivePower)
    assert not hasattr(bus, "operation")
    assert not hasattr(bus, "state")
    assert not hasattr(bus, "visualization_mode")
    assert not hasattr(bus, "magnitude")
    assert not hasattr(bus, "anarede_name")
    assert not hasattr(bus, "type")


def test_acbus_coerces_legacy_fields() -> None:
    bus = ACBus(number=1, name="Bus-1", bustype=1, area=2)

    assert bus.bustype == ACBusTypes.PV
    assert bus.bus_type == ACBusTypes.PV
    assert bus.area is not None
    assert bus.area.area_number == 2


def test_model_examples_cover_remaining_bus_types() -> None:
    dc_bus = DCBus.example()

    assert dc_bus.polarity == DCBusPolarity.POSITIVE_POLE
    assert not hasattr(dc_bus, "bustype")
    assert not hasattr(dc_bus, "area")
    assert not hasattr(dc_bus, "voltage_limits")
    assert not hasattr(dc_bus, "base_voltage")


def test_dcbus_polarity_coercion_paths() -> None:
    from_none = DCBus(name="dc-none", polarity=None)
    from_numeric = DCBus(name="dc-zero", polarity=0)
    from_blank = DCBus(name="dc-blank", polarity="   ")
    from_negative = DCBus(name="dc-neg", polarity="-")

    assert from_none.polarity == DCBusPolarity.NEUTRAL
    assert from_numeric.polarity == DCBusPolarity.NEUTRAL
    assert from_blank.polarity == DCBusPolarity.NEUTRAL
    assert from_negative.polarity == DCBusPolarity.NEGATIVE_POLE


def test_dcbus_type_enum_and_coercion_paths() -> None:
    from_none = DCBus(name="dc-none", type=None)
    from_zero = DCBus(name="dc-zero", type=0)
    from_one = DCBus(name="dc-one", type=1)
    from_blank = DCBus(name="dc-blank", type="   ")

    assert DCBusType.NO_VOLTAGE == "0"
    assert DCBusType.REFERENCE == "1"
    assert from_none.type == DCBusType.NO_VOLTAGE
    assert from_zero.type == DCBusType.NO_VOLTAGE
    assert from_one.type == DCBusType.REFERENCE
    assert from_blank.type == DCBusType.NO_VOLTAGE


def test_dcbus_ground_electrode_resistance_applies_only_to_neutral() -> None:
    positive_bus = DCBus(name="dc-pos", polarity="+", ground_electrode_resistance=1.0)
    neutral_bus = DCBus(name="dc-neu", polarity="0", ground_electrode_resistance=1.0)

    assert positive_bus.ground_electrode_resistance is None
    assert neutral_bus.ground_electrode_resistance == 1.0


def test_svc_control_mode_enum_matches_mapping() -> None:
    assert SVCControlMode.POWER == "P"
    assert SVCControlMode.CURRENT == "I"
    assert StaticVARCompensator(control_mode="I").control_mode == SVCControlMode.CURRENT


def test_dbsh_control_mode_enum_matches_mapping() -> None:
    shunt_cont = BankController(control_mode="C")
    shunt_disc = BankController(control_mode="D")
    shunt_fix = BankController(control_mode="F")

    assert ShuntControlMode.CONTINUOUS == "C"
    assert ShuntControlMode.DISCRETE == "D"
    assert ShuntControlMode.FIXED == "F"
    assert shunt_cont.control_mode == ShuntControlMode.CONTINUOUS
    assert shunt_disc.control_mode == ShuntControlMode.DISCRETE
    assert shunt_fix.control_mode == ShuntControlMode.FIXED


def test_bank_controller_control_type_enum_matches_mapping() -> None:
    assert BankControllerControlType.VOLTAGE_CONTROL_RANGE == "C"
    assert BankControllerControlType.VOLTAGE_LIMIT_VIOLATION_RANGE == "L"

    center = BankController(control_type="C")
    limit = BankController(control_type="L")

    assert center.control_type is BankControllerControlType.VOLTAGE_CONTROL_RANGE
    assert limit.control_type is BankControllerControlType.VOLTAGE_LIMIT_VIOLATION_RANGE
    # Blank/unknown tokens fall back to center-of-range control.
    assert BankController(control_type="").control_type is (
        BankControllerControlType.VOLTAGE_CONTROL_RANGE
    )


def test_converter_control_enums_and_units_match_dccv_mapping() -> None:
    converter = ConverterControl(
        converter_control_type="P",
        slack="F",
        inverter_control_mode="G",
        converter_angle=17.0,
        minimum_converter_angle=17.0,
        maximum_converter_angle=72.74,
        current_margin=10.0,
        maximum_overcurrent=40.0,
        dc_voltage_minimum_for_power_control=0.975,
        minimum_transformer_tap=0.925,
        maximum_transformer_tap=1.25,
        tap_himvar_mode=1.237,
        tap_reduced_voltage_mode=1.0,
        specified_value=1018.0,
        transformer_tap_steps="Infinity",
    )

    assert ConverterControlType.CURRENT == "C"
    assert ConverterControlType.POWER == "P"
    assert ConverterControlSlack.SLACK == "F"
    assert ConverterControlSlack.NORMAL == "N"
    assert InverterControlMode.GAMMA_CONTROLLED == "G"
    assert InverterControlMode.ACBUS_CONTROLLED == "T"
    assert converter.converter_control_type == ConverterControlType.POWER
    assert converter.slack == ConverterControlSlack.SLACK
    assert converter.inverter_control_mode == InverterControlMode.GAMMA_CONTROLLED

    assert isinstance(converter.converter_angle, Angle)
    assert isinstance(converter.minimum_converter_angle, Angle)
    assert isinstance(converter.maximum_converter_angle, Angle)
    assert isinstance(converter.current_margin, Percentage)
    assert isinstance(converter.maximum_overcurrent, Percentage)
    assert isinstance(converter.dc_voltage_minimum_for_power_control, PerUnit)
    assert isinstance(converter.minimum_transformer_tap, PerUnit)
    assert isinstance(converter.maximum_transformer_tap, PerUnit)
    assert isinstance(converter.tap_himvar_mode, PerUnit)
    assert isinstance(converter.tap_reduced_voltage_mode, PerUnit)
    assert isinstance(converter.specified_value, ActivePower)
    assert converter.specified_value.to("MW").magnitude == 1018.0
    assert math.isinf(converter.transformer_tap_steps)


def test_converter_control_current_mode_uses_ampere_units() -> None:
    converter = ConverterControl(converter_control_type="C", specified_value=1200.0)

    assert converter.converter_control_type == ConverterControlType.CURRENT
    assert isinstance(converter.specified_value, Current)
    assert converter.specified_value.to("A").magnitude == 1200.0


def test_converter_control_inverter_mode_coercion_paths() -> None:
    gamma = ConverterControl(inverter_control_mode="G")
    acbus = ConverterControl(inverter_control_mode="T")
    unknown = ConverterControl(inverter_control_mode="?")

    assert gamma.inverter_control_mode == InverterControlMode.GAMMA_CONTROLLED
    assert acbus.inverter_control_mode == InverterControlMode.ACBUS_CONTROLLED
    assert unknown.inverter_control_mode is None
    assert not hasattr(gamma, "operation")


def test_converter_control_handles_unknown_control_type_and_defaults() -> None:
    converter = ConverterControl(
        converter_control_type="X",
        slack="?",
        specified_value="321.0",
        transformer_tap_steps=None,
    )

    assert converter.converter_control_type is None
    assert converter.slack == ConverterControlSlack.NORMAL
    assert converter.specified_value == 321.0
    assert math.isinf(converter.transformer_tap_steps)


def test_converter_control_tap_steps_support_integer_and_float_values() -> None:
    discrete = ConverterControl(transformer_tap_steps="12")
    continuous = ConverterControl(transformer_tap_steps="12.5")

    assert discrete.transformer_tap_steps == 12
    assert continuous.transformer_tap_steps == 12.5


def test_converter_station_enums_and_units_match_dcnv_mapping() -> None:
    converter = ConverterStation(
        mode="I",
        current=2610.0,
        commutation_reactance=17.2,
        secondary_voltage=122.0,
        transformer_power=450.0,
        reactor_resistance=1.5,
        reactor_inductance=8.0,
        ccc_capacitance=2.0,
        frequency=60,
    )

    assert ConverterMode.RECTIFIER == "R"
    assert ConverterMode.INVERTER == "I"
    assert converter.mode == ConverterMode.INVERTER
    assert isinstance(converter.current, Current)
    assert converter.current.to("A").magnitude == 2610.0
    assert isinstance(converter.commutation_reactance, Percentage)
    assert isinstance(converter.secondary_voltage, Voltage)
    assert converter.secondary_voltage.to("kV").magnitude == 122.0
    assert isinstance(converter.transformer_power, ApparentPower)
    assert converter.transformer_power.to("MVA").magnitude == 450.0
    assert isinstance(converter.reactor_resistance, Resistance)
    assert isinstance(converter.reactor_inductance, Inductance)
    assert converter.reactor_inductance.to("millihenry").magnitude == 8.0
    assert isinstance(converter.ccc_capacitance, Capacitance)
    assert converter.ccc_capacitance.to("microfarad").magnitude == 2.0
    assert isinstance(converter.frequency, Frequency)
    assert converter.frequency.to("hertz").magnitude == 60.0
    assert not hasattr(converter, "operation")

    assert repr(converter.current) == "<Quantity(2610.0, 'A')>"
    assert repr(converter.reactor_inductance) == "<Quantity(8.0, 'mH')>"
    assert repr(converter.ccc_capacitance) == "<Quantity(2.0, 'μF')>"
    assert repr(converter.frequency) == "<Quantity(60, 'Hz')>"


def test_converter_station_mode_coercion_paths_and_defaults() -> None:
    rectifier = ConverterStation(mode="r")
    unknown = ConverterStation(mode="?")
    default = ConverterStation()

    assert rectifier.mode == ConverterMode.RECTIFIER
    assert unknown.mode is None
    assert default.mode is None
    assert isinstance(default.ccc_capacitance, Capacitance)
    assert default.ccc_capacitance.to("microfarad").magnitude == 0.0
    assert isinstance(default.reactor_inductance, Inductance)
    assert default.reactor_inductance.to("millihenry").magnitude == 0.0
    assert isinstance(default.frequency, Frequency)
    assert default.frequency.to("hertz").magnitude == 60.0


def test_converter_station_accepts_bus_instances() -> None:
    ac_bus = ACBus(name="AC_86", number=86, bustype=ACBusTypes.PQ)
    dc_bus = DCBus(name="DC_20", number=20)
    neutral_bus = DCBus(name="DC_40", number=40)
    converter = ConverterStation(
        ac_bus=ac_bus,
        dc_bus=dc_bus,
        neutral_bus=neutral_bus,
    )

    assert converter.ac_bus is ac_bus
    assert converter.dc_bus is dc_bus
    assert converter.neutral_bus is neutral_bus


def test_csc_enums_and_fields_match_mapping() -> None:
    csc = ControllableSeriesCompensator(
        control_mode="X",
        owner=Area(name="Area_2", area_number=2),
        dcsc_capacity=1992,
        initial_reactance=-0.876,
        max_reactance=-0.876,
        min_reactance=-0.876,
        specified_value=-0.876,
    )

    assert CSCControlMode.POWER == "P"
    assert CSCControlMode.CURRENT == "I"
    assert CSCControlMode.REACTANCE == "X"
    assert csc.control_mode == CSCControlMode.REACTANCE
    assert isinstance(csc.owner, Area)
    assert csc.owner.area_number == 2

    assert isinstance(csc.dcsc_capacity, ApparentPower)
    assert str(csc.dcsc_capacity.units) == "MVA"
    assert csc.dcsc_capacity.to("MVA").magnitude == 1992
    assert isinstance(csc.initial_reactance, Percentage)
    assert isinstance(csc.max_reactance, Percentage)
    assert isinstance(csc.min_reactance, Percentage)
    assert isinstance(csc.specified_value, Percentage)
    assert csc.specified_value.magnitude == -0.876

    assert not hasattr(csc, "operation")
    assert not hasattr(csc, "state")


def test_circuit_state_enum_for_line_openings() -> None:
    line = ACLine(from_bus_opening="L", to_bus_opening="D")

    assert CircuitState.CLOSED == "L"
    assert CircuitState.OPEN == "D"
    assert line.from_bus_opening == CircuitState.CLOSED
    assert line.to_bus_opening == CircuitState.OPEN


def test_csc_specified_value_units_follow_control_mode() -> None:
    csc_power = ControllableSeriesCompensator(control_mode="P", specified_value=120)
    csc_current = ControllableSeriesCompensator(control_mode="I", specified_value=0.95)
    csc_reactance = ControllableSeriesCompensator(control_mode="X", specified_value=-1.25)

    assert isinstance(csc_power.specified_value, ActivePower)
    assert csc_power.specified_value.to("MW").magnitude == 120

    assert isinstance(csc_current.specified_value, PerUnit)
    assert csc_current.specified_value.to("pu").magnitude == 0.95
    assert repr(csc_current.specified_value) == "<Quantity(0.95, 'pu')>"
    assert csc_current.specified_value.magnitude == 0.95

    assert isinstance(csc_reactance.specified_value, Percentage)
    assert csc_reactance.specified_value.magnitude == -1.25


def test_svc_slope_uses_percentage_units() -> None:
    svc = StaticVARCompensator(slope=1.2)

    assert isinstance(svc.slope, Percentage)
    assert svc.slope.magnitude == 1.2
    assert str(svc.slope.units) == "%"
    assert repr(svc.slope) == "<Quantity(1.2, '%')>"
    assert not hasattr(svc, "operation")


def test_bus_type_setter_supports_strings() -> None:
    bus = ACBus(number=1, name="Bus-1")
    bus.bus_type = "ref"

    assert bus.bustype == ACBusTypes.REF


def test_reactive_power_registry_exposes_mvar() -> None:
    quantity = 50 * ureg.MVAr

    assert quantity.magnitude == 50
    assert quantity.units == ureg.MVAr
    assert quantity.to("MVAr").magnitude == 50
    assert ReactivePower(50, "MVAr").magnitude == 50


def test_program_constant_coerces_units_and_defaults() -> None:
    base = ProgramConstant(name="BASE_1", mnemonic="BASE", value=100.0)
    tepa_default = ProgramConstant(name="TEPA_1", mnemonic="TEPA", value=None)

    assert isinstance(base.value, ApparentPower)
    assert base.value.magnitude == 100.0
    assert isinstance(tepa_default.value, ActivePower)
    assert tepa_default.value.magnitude == 0.1
    assert not hasattr(base, "available")
    assert not hasattr(base, "category")
    assert not hasattr(base, "ext")
