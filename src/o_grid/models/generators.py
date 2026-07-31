"""Generator and reactive equipment models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models.base import AnaredeComponent
from o_grid.models.enums import GenType, SVCControlMode
from o_grid.units import ActivePower, Angle, ApparentPower, Percentage, ReactivePower


class Generator(AnaredeComponent):
    """Generator dispatch and participation data (DGER)."""

    active_generation: Annotated[
        ActivePower | None,
        Field(
            description="Active power generation value from the corresponding DBAR bus, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = None
    armature_service_factor: Annotated[
        Percentage | None,
        Field(
            description="Armature current service factor, in %",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    gen_type: Annotated[
        GenType | None,
        Field(
            description=(
                "Generator technology type resolved from the gen-type mapping by bus number."
            ),
        ),
    ] = None
    load_angle: Annotated[
        Angle | None,
        Field(
            description="Maximum load angle (0.0 - 85.0), in degrees.",
            json_schema_extra={"units": "degrees"},
        ),
    ] = None
    machine_reactance: Annotated[
        Percentage | None,
        Field(
            description="Machine Reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    max_active_generation: Annotated[
        ActivePower | None,
        Field(
            description="Maximum active power generation limit value at the bus, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = ActivePower(99999.0, "MW")
    min_active_generation: Annotated[
        ActivePower | None,
        Field(
            description="Minimum active power generation limit value at the bus, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = ActivePower(0.0, "MW")
    nominal_apparent_power: Annotated[
        ApparentPower | None,
        Field(
            description="Machine nominal apparent power, in MVA",
            json_schema_extra={"units": "MVA"},
        ),
    ] = None
    nominal_power_factor: Annotated[
        int | float | str | None,
        Field(
            description="Machine Nominal Power Factor.",
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description="Bus number, as defined in the Number field of the DBAR Execution Code.",
        ),
    ] = None
    participation_factor: Annotated[
        Percentage | None,
        Field(
            description=(
                "Generation bus participation factor value, in %. The active power "
                "interchange error of each area is distributed among the area generation "
                "buses, proportionally to each one's participation factor, observing the "
                "respective minimum and maximum active power generation limits."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")
    remote_control_participation_factor: Annotated[
        Percentage | None,
        Field(
            description=(
                "Generator participation factor in the amount of reactive power needed "
                "for remote bus voltage control in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(100.0, "percent")
    rotor_service_factor: Annotated[
        Percentage | None,
        Field(
            description="Rotor current service factor, in %",
            json_schema_extra={"units": "%"},
        ),
    ] = None


class IndividualizedGeneratorGroup(AnaredeComponent):
    """Individualized generator group data (DGEI)."""

    active_generation: Annotated[
        ActivePower | None,
        Field(
            description="Active power generation value for each unit of the group, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = None
    automatic_mode: Annotated[
        str | None,
        Field(
            description=(
                "S makes the program automatically compute the number of dispatched "
                "units from the equivalent active power generation. N redefines the "
                "equivalent dispatch as the product of the units in operation by the "
                "individualized dispatch."
            ),
        ),
    ] = "N"
    bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus number, as defined in the Number field of the DBAR Execution Code, "
                "to which the individualized generator group is connected."
            ),
        ),
    ] = None
    direct_axis_reactance: Annotated[
        Percentage | None,
        Field(
            description=(
                "Direct-axis reactance of each unit of the group, in %, on the machine base."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = None
    group: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the individualized generator group.",
        ),
    ] = None
    leakage_reactance: Annotated[
        Percentage | None,
        Field(
            description="Leakage reactance of each unit of the group, in %, on the machine base.",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    maximum_reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Maximum reactive power generation limit value for each unit of the group, in Mvar."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(99999.0, "MVAr")
    mechanical_limit: Annotated[
        ActivePower | None,
        Field(
            description="Mechanical limit of each unit of the group, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = ActivePower(99999.0, "MW")
    minimum_power: Annotated[
        ActivePower | None,
        Field(
            description="Minimum power of each unit of the group, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = ActivePower(0.0, "MW")
    minimum_reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Minimum reactive power generation limit value for each unit of the group, in Mvar."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(-9999.0, "MVAr")
    minimum_units_in_operation: Annotated[
        int | float | str | None,
        Field(
            description="Minimum number of units in operation that make up the group.",
        ),
    ] = 1
    nominal_apparent_power: Annotated[
        ApparentPower | None,
        Field(
            description="Nominal apparent power in MVA of each unit of the group.",
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    nominal_power_factor: Annotated[
        int | float | str | None,
        Field(
            description="Nominal power factor of each unit of the group.",
        ),
    ] = None
    quadrature_axis_reactance: Annotated[
        Percentage | None,
        Field(
            description=(
                "Quadrature-axis reactance of each unit of the group, in %, on the machine base."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = None
    reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description="Reactive power generation value for each unit of the group, in Mvar.",
            json_schema_extra={"units": "MVAr"},
        ),
    ] = None
    step_up_transformer_reactance: Annotated[
        Percentage | None,
        Field(
            description="Step-up transformer reactance value for each unit of the group, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    units: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of identical units that make up the individualized generator group."
            ),
        ),
    ] = 1
    units_in_operation: Annotated[
        int | float | str | None,
        Field(
            description="Number of units in operation that make up the group.",
        ),
    ] = None
    voltage_droop: Annotated[
        Percentage | None,
        Field(
            description="Speed droop of each unit of the group, in % on the system base.",
            json_schema_extra={"units": "%"},
        ),
    ] = None


class StaticVARCompensator(AnaredeComponent):
    """Reactive compensation element model."""

    bus: Annotated[
        int | float | str | None,
        Field(
            description="Bus Number as defined in the Number field of the DBAR Execution Code.",
        ),
    ] = None
    control_mode: Annotated[
        SVCControlMode | None,
        Field(
            description=(
                "P – Control by power generated by the SVC.\\nI – Control by current "
                "injected by the SVC."
            ),
        ),
    ] = SVCControlMode.CURRENT
    controlled_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus Number as defined in the Number field of the DBAR Execution Code "
                "whose voltage will be controlled by the value defined in the Voltage "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identification number of the static reactive compensator group. One or "
                "more SVC groups can be connected to a bus and a group can be composed of "
                "one or more static compensators."
            ),
        ),
    ] = None
    max_reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Maximum reactive power generation limit value, in Mvar, that defines the "
                "limits of the linear part of the Static Reactive Compensator model "
                "control curve."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = None
    min_reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Minimum reactive power generation limit value, in Mvar, that defines the "
                "limits of the linear part of the Static Reactive Compensator model "
                "control curve."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = None
    reactive_generation: Annotated[
        ReactivePower | None,
        Field(
            description="Current reactive power generation value.",
            json_schema_extra={"units": "MVAr"},
        ),
    ] = None
    slope: Annotated[
        Percentage | None,
        Field(
            description=(
                "Slope value of the line that defines the linear part of the Static "
                "Reactive Compensator model control curve, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = None
    units: Annotated[
        int | float | str | None,
        Field(
            description="Number of equal units that compose the SVC group.",
        ),
    ] = None


ReactiveCompensator = StaticVARCompensator

# Backward-compatible alias.
GeneratorDispatchData = Generator
