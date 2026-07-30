"""Load and shunt models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models.base import AnaredeComponent, ParsedScalar


class CurrentInjectionLoad(AnaredeComponent):
    """Current-injection load model."""

    active_power: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Active power value of the individualized load group, in MW. If the load "
                "varies with bus voltage magnitude, enter the load value for the voltage "
                "specified in the Voltage for Load Definition field."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Bus identification number, as defined in the Bus field of the DBAR "
                "Execution Code, to which this group of individualized loads is "
                "connected."
            ),
        ),
    ] = None
    group: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Identification number of the individualized load group. Multiple groups "
                "can be connected to one bus and a group can consist of one or more "
                "individualized loads."
            ),
        ),
    ] = 1
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - addition of individualized load group data.\\nE or 1 - "
                "elimination of individualized load group data.\\nM or 2 - modification of "
                "individualized load group data."
            ),
        ),
    ] = 'A'
    parameter_a: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Portion of individualized active load that varies linearly with voltage "
                "magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    parameter_b: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Portion of individualized active load that varies with the square of "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    parameter_c: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Portion of individualized reactive load that varies linearly with "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    parameter_d: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Portion of individualized reactive load that varies with the square of "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    reactive_power: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Reactive power value of the individualized load group, in MVAr. If the "
                "load varies with bus voltage magnitude, enter the load value for the "
                "voltage specified in the Voltage for Load Definition field."
            ),
        ),
    ] = 0.0
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the load group is in operation (connected).\\nD if the load group is "
                "out of operation (disconnected)."
            ),
        ),
    ] = 'L'
    total_units: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total number of equal units that compose the individualized load group. "
                "This serves as memory of the total number of units or stages in the "
                "group."
            ),
        ),
    ] = 1
    units_in_operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of equal units or stages that compose the individualized load "
                "group that are effectively in operation."
            ),
        ),
    ] = 1
    voltage_for_load_definition: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Voltage value in p.u. for which the active and reactive load portions "
                "defined in Active Power and Reactive Power fields were measured. "
                "Implicit decimal point between columns 57 and 58."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = 1.0
    voltage_limit: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Voltage value below which the constant power portion of functional "
                "individualized loads is modeled as constant impedance, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0

class BusShunt(AnaredeComponent):
    """Bus shunt model."""

    clear_dbar_data: Annotated[
        ParsedScalar,
        Field(
            description=(
                "S if the value informed in the DBAR Capacitor/Reactor field must be "
                "cleared. Otherwise the DBAR value is preserved."
            ),
        ),
    ] = 'N'
    control_mode: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Automatic bank switching control mode: C for continuous control, D for "
                "discrete control, or F for fixed control."
            ),
        ),
    ] = 'C'
    control_type: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Voltage control type: C if control is performed by the center of the "
                "voltage range, or L if control is performed by the violated limit of the "
                "voltage range."
            ),
        ),
    ] = 'C'
    controlled_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Bus number whose voltage magnitude is controlled by automatic switching "
                "of the individualized capacitor and/or reactor banks connected to the "
                "terminal bus. The controlled voltage depends on the voltage range and "
                "the selected control type."
            ),
        ),
    ] = 'From Bus'
    dbsh_circuit: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Identification number of the parallel AC circuit when the individualized "
                "capacitor/reactor bank is connected to a transmission line."
            ),
        ),
    ] = 1
    extremity_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Bus number corresponding to the circuit extremity where the shunt "
                "capacitor/reactor bank is installed."
            ),
        ),
    ] = None
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Bus identification number to which the shunt capacitor/reactor bank is "
                "connected, or one terminal of the circuit to which the line bank is "
                "connected."
            ),
        ),
    ] = None
    initial_reactive_injection: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Initial total reactive power injection at the terminal bus, in MVAr, due "
                "to the set of capacitor and/or reactor banks connected to the bus. When "
                "Control Mode is F, this value represents the effective fixed injection "
                "at the bus."
            ),
        ),
    ] = 0.0
    maximum_voltage: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Maximum voltage limit of the control range that determines automatic "
                "bank switching action. If this field is blank, the maximum voltage is "
                "taken from the voltage limit group to which the bus belongs. Implicit "
                "decimal point between columns 25 and 26."
            ),
        ),
    ] = 'DGLT maximum voltage limit'
    minimum_voltage: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Minimum voltage limit of the control range that determines automatic "
                "bank switching action. If this field is blank, the minimum voltage is "
                "taken from the voltage limit group to which the bus belongs. Implicit "
                "decimal point between columns 20 and 21."
            ),
        ),
    ] = 'DGLT minimum voltage limit'
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - terminal bus data addition. E or 1 - terminal bus data "
                "elimination. M or 2 - terminal bus data modification."
            ),
        ),
    ] = 'A'
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Bus number of the other circuit terminal for line capacitor/reactor "
                "banks. Not used for shunt banks connected directly to an AC bus."
            ),
        ),
    ] = None

class LineShunt(AnaredeComponent):
    """Shunt bank/segment model linked to a bus shunt."""

    bank_number: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Identification number of the capacitor and/or reactor group or bank. One "
                "bus may have one or more groups or banks, and each group may consist of "
                "one or more equal switching stages."
            ),
        ),
    ] = None
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - group or bank data addition. E or 1 - group or bank data "
                "elimination. M or 2 - group or bank data modification."
            ),
        ),
    ] = 'A'
    reactive_power_per_unit: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total reactive power injected at the bus by one unit or stage of the "
                "capacitor/reactor group, in MVAr at nominal voltage (1.0 p.u.). Positive "
                "values represent capacitors and negative values represent reactors."
            ),
        ),
    ] = None
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the group or bank is in operation. D if the group or bank is out of "
                "operation."
            ),
        ),
    ] = 'L'
    total_units: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total number of equal units or stages that compose the capacitor/reactor "
                "group or bank. The maximum number of units allowed per bus is six."
            ),
        ),
    ] = None
    units_in_operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of equal units or stages of the capacitor/reactor group or bank "
                "that are effectively in operation."
            ),
        ),
    ] = 'Capacitor/Reactor units'
    parent_record_index: Annotated[
        int | None,
        Field(
            description="Parent DBSH record index for this bank row.",
        ),
    ] = None

class ShuntCompensator(BusShunt):
    """Backwards-compatible name for bus shunt components."""

    pass

class ShuntBank(LineShunt):
    """Backwards-compatible name for line shunt/bank components."""

    pass
