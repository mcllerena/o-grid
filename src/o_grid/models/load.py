"""Load and shunt models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from o_grid.models.base import AnaredeComponent
from o_grid.models.enums import BankControllerControlType, ShuntControlMode
from o_grid.units import ActivePower, Percentage, PerUnit, ReactivePower


class IndividualizedLoad(AnaredeComponent):
    """Individualized load group data model (DCAI)."""

    active_power: Annotated[
        ActivePower | None,
        Field(
            description=(
                "Active power value of the individualized load group, in MW. If the load "
                "varies with bus voltage magnitude, enter the load value for the voltage "
                "specified in the Voltage for Load Definition field."
            ),
            json_schema_extra={"units": "MW"},
        ),
    ] = ActivePower(0.0, "MW")
    bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus identification number, as defined in the Bus field of the DBAR "
                "Execution Code, to which this group of individualized loads is "
                "connected."
            ),
        ),
    ] = None
    group: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identification number of the individualized load group. Multiple groups "
                "can be connected to one bus and a group can consist of one or more "
                "individualized loads."
            ),
        ),
    ] = 1
    parameter_a: Annotated[
        Percentage | None,
        Field(
            description=(
                "Portion of individualized active load that varies linearly with voltage "
                "magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")
    parameter_b: Annotated[
        Percentage | None,
        Field(
            description=(
                "Portion of individualized active load that varies with the square of "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")
    parameter_c: Annotated[
        Percentage | None,
        Field(
            description=(
                "Portion of individualized reactive load that varies linearly with "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")
    parameter_d: Annotated[
        Percentage | None,
        Field(
            description=(
                "Portion of individualized reactive load that varies with the square of "
                "voltage magnitude, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")
    reactive_power: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Reactive power value of the individualized load group, in MVAr. If the "
                "load varies with bus voltage magnitude, enter the load value for the "
                "voltage specified in the Voltage for Load Definition field."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(0.0, "MVAr")
    total_units: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Total number of equal units that compose the individualized load group. "
                "This serves as memory of the total number of units or stages in the "
                "group."
            ),
        ),
    ] = 1
    units_in_operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of equal units or stages that compose the individualized load "
                "group that are effectively in operation."
            ),
        ),
    ] = 1
    voltage_for_load_definition: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Voltage value in p.u. for which the active and reactive load portions "
                "defined in Active Power and Reactive Power fields were measured. "
                "Implicit decimal point between columns 57 and 58."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = PerUnit(1.0, "pu")
    voltage_limit: Annotated[
        Percentage | None,
        Field(
            description=(
                "Voltage value below which the constant power portion of functional "
                "individualized loads is modeled as constant impedance, in %."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(0.0, "percent")


class BankController(AnaredeComponent):
    """DBSH bus/line-bank switching controller model."""

    clear_dbar_data: Annotated[
        int | float | str | None,
        Field(
            description=(
                "S if the value informed in the DBAR Capacitor/Reactor field must be "
                "cleared. Otherwise the DBAR value is preserved."
            ),
        ),
    ] = "N"
    control_mode: Annotated[
        ShuntControlMode | None,
        Field(
            description=(
                "Automatic bank switching control mode: C for continuous control, D for "
                "discrete control, or F for fixed control."
            ),
        ),
    ] = ShuntControlMode.CONTINUOUS
    control_type: Annotated[
        BankControllerControlType | None,
        Field(
            description=(
                "Voltage control type: C if control is performed by the center of the "
                "voltage range, or L if control is performed by the violated limit of the "
                "voltage range."
            ),
        ),
    ] = BankControllerControlType.VOLTAGE_CONTROL_RANGE
    controlled_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus number whose voltage magnitude is controlled by automatic switching "
                "of the individualized capacitor and/or reactor banks connected to the "
                "terminal bus. The controlled voltage depends on the voltage range and "
                "the selected control type."
            ),
        ),
    ] = "From Bus"
    dbsh_circuit: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identification number of the parallel AC circuit when the individualized "
                "capacitor/reactor bank is connected to a transmission line."
            ),
        ),
    ] = 1
    extremity_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus number corresponding to the circuit extremity where the shunt "
                "capacitor/reactor bank is installed."
            ),
        ),
    ] = None
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus identification number to which the shunt capacitor/reactor bank is "
                "connected, or one terminal of the circuit to which the line bank is "
                "connected."
            ),
        ),
    ] = None
    initial_reactive_injection: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Initial total reactive power injection at the terminal bus, in MVAr, due "
                "to the set of capacitor and/or reactor banks connected to the bus. When "
                "Control Mode is F, this value represents the effective fixed injection "
                "at the bus."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(0.0, "MVAr")
    maximum_voltage: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Maximum voltage limit of the control range that determines automatic "
                "bank switching action. If this field is blank, the maximum voltage is "
                "taken from the voltage limit group to which the bus belongs. Implicit "
                "decimal point between columns 25 and 26."
            ),
            json_schema_extra={"units": "pu"},
        ),
    ] = None
    minimum_voltage: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Minimum voltage limit of the control range that determines automatic "
                "bank switching action. If this field is blank, the minimum voltage is "
                "taken from the voltage limit group to which the bus belongs. Implicit "
                "decimal point between columns 20 and 21."
            ),
            json_schema_extra={"units": "pu"},
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Bus number of the other circuit terminal for line capacitor/reactor "
                "banks. Not used for shunt banks connected directly to an AC bus."
            ),
        ),
    ] = None

    @field_validator("control_mode", mode="before")
    @classmethod
    def _coerce_control_mode(cls, value: object) -> ShuntControlMode | None:
        if value is None:
            return ShuntControlMode.CONTINUOUS
        if isinstance(value, ShuntControlMode):
            return value
        text = str(value).strip().upper()
        if not text:
            return ShuntControlMode.CONTINUOUS
        if text in ShuntControlMode.__members__:
            return ShuntControlMode[text]
        return {
            "C": ShuntControlMode.CONTINUOUS,
            "D": ShuntControlMode.DISCRETE,
            "F": ShuntControlMode.FIXED,
        }.get(text, ShuntControlMode.CONTINUOUS)

    @field_validator("control_type", mode="before")
    @classmethod
    def _coerce_control_type(cls, value: object) -> BankControllerControlType | None:
        if value is None:
            return BankControllerControlType.VOLTAGE_CONTROL_RANGE
        if isinstance(value, BankControllerControlType):
            return value
        text = str(value).strip().upper()
        if not text:
            return BankControllerControlType.VOLTAGE_CONTROL_RANGE
        if text in BankControllerControlType.__members__:
            return BankControllerControlType[text]
        return {
            "C": BankControllerControlType.VOLTAGE_CONTROL_RANGE,
            "L": BankControllerControlType.VOLTAGE_LIMIT_VIOLATION_RANGE,
        }.get(text, BankControllerControlType.VOLTAGE_CONTROL_RANGE)

    @field_validator("maximum_voltage", "minimum_voltage", mode="before")
    @classmethod
    def _coerce_control_voltage(cls, value: object) -> float | PerUnit | None:
        if value is None or isinstance(value, PerUnit):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None


class ShuntBank(AnaredeComponent):
    """Base capacitor/reactor shunt bank model (DBSH bank record)."""

    bank_controller: Annotated[
        BankController | None,
        Field(
            description=(
                "Switching controller (DBSH terminal record) associated with this shunt bank."
            ),
        ),
    ] = None
    bank_number: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identification number of the capacitor and/or reactor group or bank. One "
                "bus may have one or more groups or banks, and each group may consist of "
                "one or more equal switching stages."
            ),
        ),
    ] = None
    parent_record_index: Annotated[
        int | None,
        Field(
            description="Parent DBSH record index for this bank row.",
        ),
    ] = None
    reactive_power_per_unit: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Total reactive power injected at the bus by one unit or stage of the "
                "capacitor/reactor group, in MVAr at nominal voltage (1.0 p.u.). Positive "
                "values represent capacitors and negative values represent reactors."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = None
    total_units: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Total number of equal units or stages that compose the capacitor/reactor "
                "group or bank. The maximum number of units allowed per bus is six."
            ),
        ),
    ] = None
    units_in_operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of equal units or stages of the capacitor/reactor group or bank "
                "that are effectively in operation."
            ),
        ),
    ] = "Capacitor/Reactor units"


class BusShuntBank(ShuntBank):
    """Bus-connected capacitor/reactor shunt bank (controller has no To Bus)."""


class LineShuntBank(ShuntBank):
    """Line-connected capacitor/reactor shunt bank (controller has a To Bus)."""
