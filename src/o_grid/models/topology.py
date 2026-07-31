"""Topology, bus, and area models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from o_grid.models.base import AnaredeComponent
from o_grid.models.enums import ACBusTypes
from o_grid.models.named_tuples import MinMax
from o_grid.units import Voltage


class Topology(AnaredeComponent):
    """Abstract type to represent system structure and interconnectedness."""


class AggregationTopology(Topology):
    """Base class for area-like aggregations."""


class Area(AggregationTopology):
    """Collection of buses in a given region."""

    area_number: Annotated[
        int | None,
        Field(description="Identifier of the control/operational area."),
    ] = None
    peak_active_power: Annotated[
        float,
        Field(description="Peak active power in the area", json_schema_extra={"units": "MW"}),
    ] = 0.0
    peak_reactive_power: Annotated[
        float,
        Field(description="Peak reactive power in the area", json_schema_extra={"units": "MVAR"}),
    ] = 0.0
    load_response: Annotated[
        float,
        Field(
            description=(
                "Load-frequency damping parameter modeling how much area load "
                "changes due to frequency (MW/Hz)."
            )
        ),
    ] = 0.0

    @classmethod
    def example(cls) -> Area:
        return Area(name="ExampleArea")


class LoadZone(AggregationTopology):
    """Collection of buses for load aggregation/analysis."""

    load_zone_number: Annotated[
        int | None,
        Field(description="Identifier of the load zone."),
    ] = None
    peak_active_power: Annotated[
        float,
        Field(description="Peak active power in the load zone", json_schema_extra={"units": "MW"}),
    ] = 0.0
    peak_reactive_power: Annotated[
        float,
        Field(
            description="Peak reactive power in the load zone", json_schema_extra={"units": "MVAR"}
        ),
    ] = 0.0

    @classmethod
    def example(cls) -> LoadZone:
        return LoadZone(name="ExampleLoadZone")


class Bus(Topology):
    """Abstract class for a bus."""

    number: Annotated[
        int | None,
        Field(description="A unique bus identification number."),
    ] = None
    bustype: Annotated[
        ACBusTypes | None,
        Field(description="Type/category of bus."),
    ] = None
    area: Annotated[
        Area | None,
        Field(description="Area containing the bus."),
    ] = None
    load_zone: Annotated[
        LoadZone | None,
        Field(description="Load zone containing the bus."),
    ] = None
    voltage_limits: Annotated[
        MinMax | None,
        Field(description="Voltage limits (min, max)."),
    ] = None
    base_voltage: Annotated[
        Voltage | None,
        Field(description="Base voltage in kV.", json_schema_extra={"units": "kV"}),
    ] = None
    magnitude: Annotated[
        float | None,
        Field(description="Voltage as a multiple of base voltage."),
    ] = None

    @field_validator("area", mode="before")
    @classmethod
    def _coerce_area(cls, value: object) -> Area | None:
        if value is None or isinstance(value, Area):
            return value
        if isinstance(value, int):
            return Area(name=f"Area_{value}", area_number=value)
        return Area(name=str(value), area_number=None)

    @field_validator("load_zone", mode="before")
    @classmethod
    def _coerce_load_zone(cls, value: object) -> LoadZone | None:
        if value is None or isinstance(value, LoadZone):
            return value
        if isinstance(value, int):
            return LoadZone(name=f"LoadZone_{value}", load_zone_number=value)
        return LoadZone(name=str(value), load_zone_number=None)


class Arc(Topology):
    """Topological directed edge connecting two buses."""

    from_to: Annotated[Bus | int | None, Field(description="The initial bus", alias="from")] = None
    to_from: Annotated[Bus | int | None, Field(description="The terminal bus", alias="to")] = None


class ACBus(Bus):
    """AC bus model."""

    voltage_base_group_data: Annotated[
        VoltageBaseGroup | None,
        Field(
            description=("Resolved voltage base group record associated with this bus."),
            exclude=True,
        ),
    ] = None

    @field_validator("bustype", mode="before")
    @classmethod
    def _coerce_bus_type(cls, value: object) -> ACBusTypes | None:
        if value is None or value == "":
            return ACBusTypes.PQ
        if isinstance(value, ACBusTypes):
            return value
        if isinstance(value, int):
            return {0: ACBusTypes.PQ, 1: ACBusTypes.PV, 2: ACBusTypes.REF}.get(value, ACBusTypes.PQ)
        text = str(value).strip().upper()
        if not text:
            return ACBusTypes.PQ
        return ACBusTypes[text] if text in ACBusTypes.__members__ else ACBusTypes.PQ

    @property
    def bus_type(self) -> ACBusTypes | None:
        return self.bustype

    @bus_type.setter
    def bus_type(self, value: ACBusTypes | int | str | None) -> None:
        self.bustype = self._coerce_bus_type(value)

    voltage_limit_group_data: Annotated[
        VoltageLimitGroup | None,
        Field(
            description=("Resolved voltage limit group record associated with this bus."),
            exclude=True,
        ),
    ] = None

    active_generation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Active power generation value at the bus, in MW. This field defines the "
                "base operating point over which control actions are executed to maintain "
                "the programmed active power exchange between areas. Active power "
                "exchange errors between areas are distributed among area generators, "
                "based on this value and according to each generator's participation."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    active_load: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus active load value, in MW. In case the load varies with bus voltage "
                "magnitude, enter in this field the load value for the voltage specified "
                "in the Voltage For Load Definition field."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    angle: Annotated[
        int | float | str | None,
        Field(
            description="Initial phase angle of bus voltage, in degrees.",
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    area: Annotated[
        Area | int | None,
        Field(
            description="Number of the area to which the bus belongs.",
        ),
    ] = 1
    capacitor_reactor: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Total reactive power injected at the bus, in MVAr, by capacitor/reactor "
                "banks. The value to be filled in this field refers to the reactive power "
                "injected at nominal voltage (1.0 p.u.). This value must be positive for "
                "capacitors and negative for reactors."
            ),
        ),
    ] = 0.0
    controlled_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "For voltage regulated and reference buses, with specified reactive power "
                "limits, this field is for the number of the bus whose voltage magnitude "
                "will be controlled. The voltage magnitude value to be maintained is "
                "obtained from the Voltage field of the record relative to the bus."
            ),
        ),
    ] = None
    max_reactive_generation: Annotated[
        int | float | str | None,
        Field(
            description="Maximum reactive power generation limit value at the bus, in MVAr.",
        ),
    ] = None
    min_reactive_generation: Annotated[
        int | float | str | None,
        Field(
            description="Minimum reactive power generation limit value at the bus, in MVAr.",
        ),
    ] = None
    anarede_name: Annotated[
        int | float | str | None,
        Field(
            description="Alphanumeric identification of the bus.",
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of AC bus.",
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "A or 0 - Bus data addition.\\nE or 1 - Elimination of bus data.\\nM or 2 - "
                "Modification of bus data."
            ),
        ),
    ] = "A"
    reactive_generation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Reactive power generation value at the bus, in MVAr. For load bus this "
                "value is fixed. For load bus with voltage limit this value is kept "
                "constant, while voltage magnitude remains between specified limits. For "
                "voltage regulated and reference buses with specified reactive power "
                "generation limits, this field can be left blank."
            ),
        ),
    ] = 0.0
    reactive_load: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus reactive load value, in MVAr. In case the load varies with bus "
                "voltage magnitude, enter in this field the load value for the voltage "
                "specified in the Voltage For Load Definition field."
            ),
        ),
    ] = 0.0
    state: Annotated[
        int | float | str | None,
        Field(
            description=(
                "L - Bus in service (connected/ligado) \\nD - Bus out of service "
                "(disconnected/desligado)"
            ),
        ),
    ] = "L"
    type: Annotated[
        int | float | str | None,
        Field(
            description=(
                "0 - Load bus (PQ - Fixed active and reactive power injections).\\n1 - "
                "Voltage regulated bus (PV - Fixed active power injection and voltage "
                "magnitude).\\n2 - Reference bus (V - Fixed voltage magnitude and phase "
                "angle).\\n3 - Load bus with voltage limits (PQ - Fixed active and "
                "reactive power injections while voltage magnitude remains within limit "
                "values)."
            ),
        ),
    ] = 0
    visualization_mode: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Enter in this field the AC bus visualization mode in the single-line "
                "diagram:\\n0 - normal bus.\\n1 - midpoint bus.\\n2 - auxiliary bus."
            ),
        ),
    ] = 0
    voltage: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Initial value of voltage magnitude, in p.u. For voltage controlled bus, "
                "remotely or not, by reactive power generation or transformer tap "
                "variation, this field must be filled with the voltage magnitude value to "
                "be kept constant. Implicit decimal point between columns 25 and 26."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = 1.0
    voltage_base_group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Voltage Base Group identifier to which the AC bus belongs, composed of "
                "up to two characters of digit type (0 to 9) or character (A to Z), as "
                "defined in the DGBT Execution Code. The values associated with Voltage "
                "Base Groups are defined in the DGBT execution code. Groups that are not "
                "defined will have a value equal to 1 kV."
            ),
        ),
    ] = "0"
    voltage_for_load_definition: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Enter in this field the p.u. voltage value for which the active and "
                "reactive load portions defined in the Active Load and Reactive Load "
                "fields, respectively, were measured. Implicit decimal point between "
                "columns 77 and 78."
            ),
        ),
    ] = 1.0
    voltage_limit_group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Voltage Limit Group identifier to which the AC bus belongs, composed of "
                "up to two characters of digit type (0 to 9) or character (A to Z), as "
                "defined in the DGLT Execution Code. The values associated with Voltage "
                "Limit Groups are defined in the DGLT Execution Code. Groups that are not "
                "defined will have minimum and maximum voltage limit values equal to 0.8 "
                "and 1.2 pu, respectively."
            ),
        ),
    ] = 0

    @classmethod
    def example(cls) -> ACBus:
        return ACBus(
            number=1,
            name="ExampleACBus",
            area=Area.example(),
            bustype=ACBusTypes.PV,
            base_voltage=Voltage(138.0, "kV"),
            voltage_limits=MinMax(min=0.9, max=1.1),
        )


class DCBus(Bus):
    """DC bus model."""

    dc_link_number: Annotated[
        int | float | str | None,
        Field(
            description=(
                "DC link number, as defined in the Number field of the DELO execution "
                "code. All buses of the same pole or bipole must belong to the same DC "
                "link."
            ),
        ),
    ] = 0
    ground_electrode_resistance: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Ground electrode resistance, in ohms, for a neutral bus. This field must "
                "not be filled for positive- or negative-polarity buses."
            ),
            json_schema_extra={"units": "ohm"},
        ),
    ] = 1.0
    anarede_name: Annotated[
        int | float | str | None,
        Field(
            description="Alphanumeric identification of the DC bus.",
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description="DC bus identification number.",
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description="A or 0 - DC bus data addition. M or 2 - DC bus data modification.",
        ),
    ] = "A"
    polarity: Annotated[
        int | float | str | None,
        Field(
            description=(
                "+ indicates that the bus belongs to the positive pole. - indicates that "
                "the bus belongs to the negative pole. 0 indicates a neutral bus."
            ),
        ),
    ] = "0"
    type: Annotated[
        int | float | str | None,
        Field(
            description=(
                "0 - bus without specified voltage. 1 - bus with specified voltage, used "
                "as a reference bus. One type-1 bus must be specified for each pole of "
                "each DC link."
            ),
        ),
    ] = 0
    voltage: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Initial voltage magnitude of the DC bus, in kV. For type-1 buses this "
                "field contains the voltage value to be held constant."
            ),
            json_schema_extra={"units": "kV"},
        ),
    ] = None
    voltage_limit_group: Annotated[
        int | float | str | None,
        Field(
            description="Voltage limit group identifier associated with the DC bus.",
        ),
    ] = 0

    @classmethod
    def example(cls) -> DCBus:
        return DCBus(number=1, name="ExampleDCBus", area=Area.example(), bustype=ACBusTypes.PV)


class VoltageLimitGroup(AnaredeComponent):
    """Voltage operating limit group."""

    emergency_maximum_voltage_limit: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum voltage limit, in p.u., associated with the voltage limit group "
                "under emergency conditions."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = "Maximum voltage limit"
    emergency_minimum_voltage_limit: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum voltage limit, in p.u., associated with the voltage limit group "
                "under emergency conditions."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = "Minimum voltage limit"
    group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Voltage limit group identifier, as defined in the Voltage Limit Group "
                "field of the DBAR execution code."
            ),
        ),
    ] = None
    maximum_voltage_limit: Annotated[
        int | float | str | None,
        Field(
            description="Maximum voltage limit, in p.u., associated with the voltage limit group.",
            json_schema_extra={"units": "p.u."},
        ),
    ] = 1.2
    minimum_voltage_limit: Annotated[
        int | float | str | None,
        Field(
            description="Minimum voltage limit, in p.u., associated with the voltage limit group.",
            json_schema_extra={"units": "p.u."},
        ),
    ] = 0.8


class VoltageBaseGroup(AnaredeComponent):
    """Voltage base group."""

    group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Voltage base group identifier, as defined in the Voltage Base Group "
                "field of the DBAR execution code."
            ),
        ),
    ] = 0
    voltage: Annotated[
        int | float | str | None,
        Field(
            description="Base voltage associated with the group, in kV.",
            json_schema_extra={"units": "kV"},
        ),
    ] = 1.0


class ControlArea(AnaredeComponent):
    """Control area model."""

    area_number: Annotated[
        int | float | str | None,
        Field(
            description="Area number, as defined in the Area field of the DBAR execution code.",
        ),
    ] = None
    maximum_net_interchange: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum net active power interchange of the area, in MW. Positive values "
                "indicate export and negative values indicate import."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    minimum_net_interchange: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum net active power interchange of the area, in MW. Positive values "
                "indicate export and negative values indicate import."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    anarede_name: Annotated[
        int | float | str | None,
        Field(
            description="Alphanumeric identification of the area.",
        ),
    ] = None
    net_interchange: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Net active power interchange of the area, in MW. Positive values "
                "indicate export and negative values indicate import."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
