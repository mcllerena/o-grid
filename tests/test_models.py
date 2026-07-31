from __future__ import annotations

from o_grid.models import (
    ACBranch,
    ACBus,
    ACBusTypes,
    ACLine,
    Area,
    Branch,
    BusShunt,
    ControllableSeriesCompensator,
    CSCControlMode,
    DCBus,
    Line,
    LineShunt,
    MinMax,
    PhaseShiftingTransformer,
    StaticVARCompensator,
    SVCControlMode,
    TapChangingTransformer,
    TapTransformer,
    TapTransformerControl,
)
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Percentage,
    PerUnit,
    ReactivePower,
    Voltage,
    ureg,
)


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
    assert DCBus.example().bustype == ACBusTypes.PV


def test_svc_control_mode_enum_matches_mapping() -> None:
    assert SVCControlMode.POWER == "P"
    assert SVCControlMode.CURRENT == "I"
    assert StaticVARCompensator(control_mode="I").control_mode == SVCControlMode.CURRENT


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
