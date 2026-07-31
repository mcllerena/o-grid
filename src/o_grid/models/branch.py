"""Branch and network element models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from o_grid.models.base import AnaredeComponent
from o_grid.models.control import DCLineData
from o_grid.models.enums import CircuitState, CSCControlMode
from o_grid.models.named_tuples import FromToToFrom, MinMax
from o_grid.models.topology import ACBus, Arc, Area, DCBus
from o_grid.units import (
    ActivePower,
    ApparentPower,
    Inductance,
    Percentage,
    PerUnit,
    ReactivePower,
    Resistance,
    get_magnitude,
)

CtapOption = Annotated[
    bool,
    Field(
        description=(
            "Fixation in the voltage control application using automatic tap changing (CTAP)."
        ),
    ),
]
FlowMonitoring = Annotated[
    bool,
    Field(
        description="Reading of AC circuit flow monitoring data (DMFL CIRC).",
    ),
]


class Branch(AnaredeComponent):
    """Class representing a connection between components."""

    @classmethod
    def example(cls) -> Branch:
        return Branch(name="ExampleBranch")


class ACBranch(Branch):
    """Class representing an AC connection between components."""

    arc: Annotated[Arc | None, Field(description="The branch's connections.")] = None
    r: Annotated[
        Percentage | None,
        Field(description="Resistance of the branch, in %."),
    ] = None
    x: Annotated[
        Percentage | None,
        Field(description="Reactance of the branch, in %."),
    ] = None
    rating: Annotated[
        ApparentPower | None,
        Field(description="Thermal rating of the line, in MVA."),
    ] = None


class Line(ACBranch):
    """Class representing an AC transmission line."""

    b: Annotated[FromToToFrom | None, Field(description="Shunt susceptance in MVAr")] = None
    g: Annotated[FromToToFrom | None, Field(description="Shunt conductance in MW")] = None
    angle_limits: Annotated[MinMax | None, Field(description="The branch angle limits")] = None

    @classmethod
    def example(cls) -> Line:
        return Line(
            name="ExampleLine",
            arc=Arc(from_to=ACBus.example(), to_from=ACBus.example()),
            rating=ApparentPower(100, "MVA"),
            angle_limits=MinMax(min=-0.03, max=0.03),
        )


class ACLine(Line):
    """AC transmission line model."""

    ctap_option: CtapOption = False
    flow_monitoring: FlowMonitoring = False
    controlled_bus: Annotated[
        ACBus | None,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = None
    line_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = None
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED
    normal_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    number_of_taps: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    owner: Annotated[
        Area | None,
        Field(
            description=(
                "Area that owns the line. This is resolved from the selected terminal "
                "bus area during parsing."
            ),
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED


class ControllableSeriesCompensator(AnaredeComponent):
    """Series compensation element model."""

    ctap_option: CtapOption = False
    flow_monitoring: FlowMonitoring = False
    bypass: Annotated[
        int | float | str | None,
        Field(
            description=(
                "L if the bypass switch is closed (connected).\\nD if the bypass switch is "
                "open (disconnected)."
            ),
        ),
    ] = "D"
    control_mode: Annotated[
        CSCControlMode | None,
        Field(
            description=(
                "P - Constant power. The specified value for active power flow in the "
                "circuit is maintained while CSC reactance values remain within "
                "limits.\\nI - Constant current. The specified value for current magnitude "
                "in the circuit is maintained while CSC reactance values remain within "
                "limits.\\nX - Constant reactance. The CSC does not act and reactance is "
                "fixed at the specified value."
            ),
        ),
    ] = CSCControlMode.REACTANCE
    dcsc_capacity: Annotated[
        ApparentPower | None,
        Field(
            description="CSC nominal capacity, in MVA.",
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(9999.0, "MVA")
    dcsc_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at one end of the CSC as defined in the Number field "
                "of the DBAR Execution Code."
            ),
        ),
    ] = None
    initial_reactance: Annotated[
        Percentage | None,
        Field(
            description="Initial value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    max_reactance: Annotated[
        Percentage | None,
        Field(
            description="Maximum value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(9999.0, "%")
    measurement_terminal: Annotated[
        ACBus | None,
        Field(
            description=(
                "Number of the CSC terminal bus at which power or current is measured, as "
                "defined in the Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    min_reactance: Annotated[
        Percentage | None,
        Field(
            description="Minimum value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(-9999.0, "%")
    number_of_stages: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of stages of the discrete CSC (TSSC - Thyristor Switched Series "
                "Capacitor). The default value is for CSC operating in continuous mode "
                "(TCSC - Thyristor Controlled Series Capacitor)."
            ),
        ),
    ] = None
    owner: Annotated[
        Area | None,
        Field(
            description=(
                "Area that owns the CSC. This is resolved from the selected terminal "
                "bus area during parsing."
            ),
        ),
    ] = None
    specified_value: Annotated[
        ActivePower | PerUnit | Percentage | float | None,
        Field(
            description=(
                "Active Power Flow in the CSC, in MW, if the specified control mode is "
                "Constant Power (P), or; CSC Current Magnitude, in pu, if the specified "
                "control mode is Constant Current (I), or; CSC Reactance, in %, if the "
                "specified control mode is Constant Reactance (X)."
            ),
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at the other end of the CSC as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def _coerce_specified_value_units(self) -> ControllableSeriesCompensator:
        value = self.specified_value
        if value is None:
            return self

        magnitude = get_magnitude(value)
        if isinstance(magnitude, str):
            text = magnitude.strip()
            if not text:
                object.__setattr__(self, "specified_value", None)
                return self
            magnitude = float(text)

        mode = self.control_mode or CSCControlMode.REACTANCE
        if mode == CSCControlMode.POWER:
            object.__setattr__(self, "specified_value", ActivePower(float(magnitude), "MW"))
        elif mode == CSCControlMode.CURRENT:
            object.__setattr__(self, "specified_value", PerUnit(float(magnitude), "pu"))
        else:
            object.__setattr__(self, "specified_value", Percentage(float(magnitude), "%"))
        return self


SeriesCompensator = ControllableSeriesCompensator


class LTCTransformer(AnaredeComponent):
    """Load Tap Changer Transformer derived from line tap values."""

    ctap_option: CtapOption = False
    flow_monitoring: FlowMonitoring = False
    controlled_bus: Annotated[
        ACBus | None,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = None
    line_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED
    normal_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    number_of_taps: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    owner: Annotated[
        Area | None,
        Field(
            description=(
                "Area that owns the line. This is resolved from the selected terminal "
                "bus area during parsing."
            ),
        ),
    ] = None
    r: Annotated[
        Percentage | None,
        Field(description="Resistance of the branch, in %."),
    ] = None
    x: Annotated[
        Percentage | None,
        Field(description="Reactance of the branch, in %."),
    ] = None
    rating: Annotated[
        ApparentPower | None,
        Field(description="Thermal rating of the line, in MVA."),
    ] = None
    b: Annotated[FromToToFrom | None, Field(description="Shunt susceptance in MVAr")] = None
    tap: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Tap value referred to the bus defined in the From Bus field, in p.u., "
                "for fixed tap transformers or an estimate of this value for automatic "
                "tap changing transformers (LTC). Implicit decimal point between columns "
                "40 and 41."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_maximum: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Maximum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 50 and 51."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_minimum: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Minimum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 45 and 46."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED


TapChangingTransformer = LTCTransformer


class PhaseShiftingTransformer(AnaredeComponent):
    """Phase-shifting transformer derived from line phase-shift angle."""

    ctap_option: CtapOption = False
    flow_monitoring: FlowMonitoring = False
    controlled_bus: Annotated[
        ACBus | None,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = None
    line_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED
    normal_capacity: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = ApparentPower(99999.0, "MVA")
    number_of_taps: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    owner: Annotated[
        Area | None,
        Field(
            description=(
                "Area that owns the line. This is resolved from the selected terminal "
                "bus area during parsing."
            ),
        ),
    ] = None
    r: Annotated[
        Percentage | None,
        Field(description="Resistance of the branch, in %."),
    ] = None
    x: Annotated[
        Percentage | None,
        Field(description="Reactance of the branch, in %."),
    ] = None
    rating: Annotated[
        ApparentPower | None,
        Field(description="Thermal rating of the line, in MVA."),
    ] = None
    b: Annotated[FromToToFrom | None, Field(description="Shunt susceptance in MVAr")] = None
    tap: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Tap value referred to the bus defined in the From Bus field, in p.u., "
                "for fixed tap transformers or an estimate of this value for automatic "
                "tap changing transformers (LTC). Implicit decimal point between columns "
                "40 and 41."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_maximum: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Maximum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 50 and 51."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_minimum: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Minimum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 45 and 46."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        CircuitState | None,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = CircuitState.CLOSED


class LineShunt(AnaredeComponent):
    """DSHL AC-circuit terminal shunt model."""

    ctap_option: CtapOption = False
    flow_monitoring: FlowMonitoring = False
    dshl_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at one end of the AC circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    shunt_from: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Reactive power of shunts at the end defined in the From Bus field for "
                "nominal voltage (1.0 p.u.), in MVAr."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(0.0, "MVAr")
    shunt_to: Annotated[
        ReactivePower | None,
        Field(
            description=(
                "Reactive power of shunts at the end defined in the To Bus field for "
                "nominal voltage (1.0 p.u.), in MVAr."
            ),
            json_schema_extra={"units": "MVAr"},
        ),
    ] = ReactivePower(0.0, "MVAr")
    state_from: Annotated[
        CircuitState | None,
        Field(
            description=(
                "L if the line shunt at this end is in operation (connected).\\nD if the "
                "line shunt at this end is out of operation (disconnected)."
            ),
        ),
    ] = CircuitState.CLOSED
    state_to: Annotated[
        CircuitState | None,
        Field(
            description=(
                "L if the line shunt at this end is in operation (connected).\\nD if the "
                "line shunt at this end is out of operation (disconnected)."
            ),
        ),
    ] = CircuitState.CLOSED
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None


class DCLine(AnaredeComponent):
    """DC line model."""

    capacity: Annotated[
        ActivePower | None,
        Field(
            description=(
                "DC line loading capacity, in MW, for flow monitoring purposes. "
                "Defaults to 9999 (unlimited) when not specified."
            ),
        ),
    ] = ActivePower(9999, "MW")
    dcli_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel DC line.",
        ),
    ] = None

    from_bus: Annotated[
        DCBus | int | float | str | None,
        Field(
            description=(
                "Number of the DC bus at one end of the DC line, as defined in the Number "
                "field of the DCBA execution code."
            ),
        ),
    ] = None
    inductance: Annotated[
        Inductance | None,
        Field(
            description="DC line inductance, in mH.",
        ),
    ] = Inductance(0.0, "millihenry")
    line_data: Annotated[
        DCLineData | None,
        Field(
            description="DC link data (DELO record) associated with this DC line.",
        ),
    ] = None
    owner: Annotated[
        int | float | str | None,
        Field(
            description="Owner flag. This field is not used in this version.",
        ),
    ] = None
    resistance: Annotated[
        Resistance | None,
        Field(
            description="DC line resistance, in ohms.",
        ),
    ] = None
    to_bus: Annotated[
        DCBus | int | float | str | None,
        Field(
            description=(
                "Number of the DC bus at the other end of the DC line, as defined in the "
                "Number field of the DCBA execution code."
            ),
        ),
    ] = None


class TransferFunctionCircuit(AnaredeComponent):
    """Circuit selector row for transfer-function constraints."""

    circuit_1: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the first selected parallel AC circuit.",
        ),
    ] = None
    circuit_2: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the second selected parallel AC circuit.",
        ),
    ] = None
    circuit_3: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the third selected parallel AC circuit.",
        ),
    ] = None
    circuit_4: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the fourth selected parallel AC circuit.",
        ),
    ] = None
    circuit_5: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the fifth selected parallel AC circuit.",
        ),
    ] = None
    from_bus_1: Annotated[
        int | float | str | None,
        Field(
            description="From bus of the first selected circuit.",
        ),
    ] = None
    from_bus_2: Annotated[
        int | float | str | None,
        Field(
            description="From bus of the second selected circuit.",
        ),
    ] = None
    from_bus_3: Annotated[
        int | float | str | None,
        Field(
            description="From bus of the third selected circuit.",
        ),
    ] = None
    from_bus_4: Annotated[
        int | float | str | None,
        Field(
            description="From bus of the fourth selected circuit.",
        ),
    ] = None
    from_bus_5: Annotated[
        int | float | str | None,
        Field(
            description="From bus of the fifth selected circuit.",
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "A - addition of fixed CTAP-control data. E - elimination of fixed "
                "CTAP-control data."
            ),
        ),
    ] = "A"
    to_bus_1: Annotated[
        int | float | str | None,
        Field(
            description="To bus of the first selected circuit.",
        ),
    ] = None
    to_bus_2: Annotated[
        int | float | str | None,
        Field(
            description="To bus of the second selected circuit.",
        ),
    ] = None
    to_bus_3: Annotated[
        int | float | str | None,
        Field(
            description="To bus of the third selected circuit.",
        ),
    ] = None
    to_bus_4: Annotated[
        int | float | str | None,
        Field(
            description="To bus of the fourth selected circuit.",
        ),
    ] = None
    to_bus_5: Annotated[
        int | float | str | None,
        Field(
            description="To bus of the fifth selected circuit.",
        ),
    ] = None


class FlowMonitoringCircuit(TransferFunctionCircuit):
    """Circuit selector row for AC circuit flow monitoring (DMFL CIRC)."""
