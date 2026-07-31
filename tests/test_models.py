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
    DCBus,
    Line,
    LineShunt,
    LoadZone,
    MinMax,
    PhaseShiftingTransformer,
    StaticVARCompensator,
    TapChangingTransformer,
    TapTransformer,
    TapTransformerControl,
)
from o_grid.units import Voltage


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


def test_acbus_example_uses_r2x_style_fields() -> None:
    bus = ACBus.example()

    assert bus.bustype == ACBusTypes.PV
    assert isinstance(bus.base_voltage, Voltage)
    assert bus.base_voltage.magnitude == 138.0
    assert bus.voltage_limits == MinMax(min=0.9, max=1.1)


def test_acbus_coerces_legacy_fields() -> None:
    bus = ACBus(number=1, name="Bus-1", bustype=1, area=2, load_zone="Zone A")

    assert bus.bustype == ACBusTypes.PV
    assert bus.bus_type == ACBusTypes.PV
    assert bus.area is not None
    assert bus.area.area_number == 2
    assert bus.load_zone is not None
    assert bus.load_zone.name == "Zone A"


def test_model_examples_cover_remaining_bus_types() -> None:
    assert LoadZone.example().name == "ExampleLoadZone"
    assert DCBus.example().bustype == ACBusTypes.PV


def test_bus_type_setter_supports_strings() -> None:
    bus = ACBus(number=1, name="Bus-1")
    bus.bus_type = "ref"

    assert bus.bustype == ACBusTypes.REF