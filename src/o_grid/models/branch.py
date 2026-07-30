"""Branch and network element models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models.base import AnaredeComponent, ParsedScalar


class ACLine(AnaredeComponent):
    """AC transmission line model."""

    controlled_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = 'From Bus'
    dlin_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 'Normal Capacity'
    equipment_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Loading capacity of the equipment with the smallest loading capacity "
                "connected to the circuit."
            ),
        ),
    ] = 'Normal Capacity'
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'
    normal_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 99999.0
    number_of_taps: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - Circuit data addition.\\nE or 1 - Circuit data elimination.\\nM "
                "or 2 - Circuit data modification."
            ),
        ),
    ] = 'A'
    owner: Annotated[
        ParsedScalar,
        Field(
            description=(
                "F if the circuit belongs to the area of the bus defined in the From Bus "
                "field.\\nT if the circuit belongs to the area of the bus defined in the "
                "To Bus field."
            ),
        ),
    ] = 'F'
    phase_shift: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Phase shift angle value, in degrees, for phase shifting transformers. "
                "The specified angular phase shift is applied relative to the angle of "
                "the bus defined in the From Bus field. Implicit decimal point between "
                "columns 56 and 57."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    reactance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit reactance value, in %. For transformers this value corresponds "
                "to the reactance value for the nominal tap. Implicit decimal point "
                "between columns 30 and 31."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    resistance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit resistance value, in %. For transformers this value corresponds "
                "to the resistance value for the nominal tap. Implicit decimal point "
                "between columns 24 and 25."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the circuit is in operation (connected).\\nD if the circuit is out "
                "of operation (disconnected)."
            ),
        ),
    ] = 'L'
    susceptance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total shunt susceptance value of the circuit, in Mvar. Implicit decimal "
                "point between columns 35 and 36."
            ),
        ),
    ] = 0.0
    tap: Annotated[
        ParsedScalar,
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
        ParsedScalar,
        Field(
            description=(
                "Maximum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 50 and 51."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_minimum: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Minimum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 45 and 46."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'

class SeriesCompensator(AnaredeComponent):
    """Series compensation element model."""

    bypass: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the bypass switch is closed (connected).\\nD if the bypass switch is "
                "open (disconnected)."
            ),
        ),
    ] = 'D'
    control_mode: Annotated[
        ParsedScalar,
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
    ] = 'X'
    dcsc_capacity: Annotated[
        ParsedScalar,
        Field(
            description="CSC nominal capacity, in MVA.",
            json_schema_extra={"units": "MVA"},
        ),
    ] = 9999.0
    dcsc_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at one end of the CSC as defined in the Number field "
                "of the DBAR Execution Code."
            ),
        ),
    ] = None
    initial_reactance: Annotated[
        ParsedScalar,
        Field(
            description="Initial value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = None
    max_reactance: Annotated[
        ParsedScalar,
        Field(
            description="Maximum value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = 9999.0
    measurement_terminal: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the CSC terminal bus at which power or current is measured, as "
                "defined in the Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    min_reactance: Annotated[
        ParsedScalar,
        Field(
            description="Minimum value of CSC reactance, in %.",
            json_schema_extra={"units": "%"},
        ),
    ] = -9999.0
    number_of_stages: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of stages of the discrete CSC (TSSC - Thyristor Switched Series "
                "Capacitor). The default value is for CSC operating in continuous mode "
                "(TCSC - Thyristor Controlled Series Capacitor)."
            ),
        ),
    ] = None
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - CSC data addition.\\nE or 1 - CSC data elimination.\\nM or 2 - "
                "CSC data modification."
            ),
        ),
    ] = 'A'
    owner: Annotated[
        ParsedScalar,
        Field(
            description=(
                "F if the circuit belongs to the area of the bus defined in the From Bus "
                "field.\\nT if the circuit belongs to the area of the bus defined in the "
                "To Bus field."
            ),
        ),
    ] = 'F'
    specified_value: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Active Power Flow in the CSC, in MW, if the specified control mode is "
                "Constant Power (P), or; CSC Current Magnitude, in pu, if the specified "
                "control mode is Constant Current (I), or; CSC Reactance, in %, if the "
                "specified control mode is Constant Reactance (X)."
            ),
        ),
    ] = None
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the circuit is in operation (connected).\\nD if the circuit is out "
                "of operation (disconnected)."
            ),
        ),
    ] = 'L'
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at the other end of the CSC as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None

class TapChangingTransformer(AnaredeComponent):
    """Tap-changing transformer derived from line tap values."""

    controlled_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = 'From Bus'
    dlin_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 'Normal Capacity'
    equipment_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Loading capacity of the equipment with the smallest loading capacity "
                "connected to the circuit."
            ),
        ),
    ] = 'Normal Capacity'
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'
    normal_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 99999.0
    number_of_taps: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - Circuit data addition.\\nE or 1 - Circuit data elimination.\\nM "
                "or 2 - Circuit data modification."
            ),
        ),
    ] = 'A'
    owner: Annotated[
        ParsedScalar,
        Field(
            description=(
                "F if the circuit belongs to the area of the bus defined in the From Bus "
                "field.\\nT if the circuit belongs to the area of the bus defined in the "
                "To Bus field."
            ),
        ),
    ] = 'F'
    phase_shift: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Phase shift angle value, in degrees, for phase shifting transformers. "
                "The specified angular phase shift is applied relative to the angle of "
                "the bus defined in the From Bus field. Implicit decimal point between "
                "columns 56 and 57."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    reactance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit reactance value, in %. For transformers this value corresponds "
                "to the reactance value for the nominal tap. Implicit decimal point "
                "between columns 30 and 31."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    resistance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit resistance value, in %. For transformers this value corresponds "
                "to the resistance value for the nominal tap. Implicit decimal point "
                "between columns 24 and 25."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the circuit is in operation (connected).\\nD if the circuit is out "
                "of operation (disconnected)."
            ),
        ),
    ] = 'L'
    susceptance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total shunt susceptance value of the circuit, in Mvar. Implicit decimal "
                "point between columns 35 and 36."
            ),
        ),
    ] = 0.0
    tap: Annotated[
        ParsedScalar,
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
        ParsedScalar,
        Field(
            description=(
                "Maximum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 50 and 51."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_minimum: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Minimum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 45 and 46."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'

class PhaseShiftingTransformer(AnaredeComponent):
    """Phase-shifting transformer derived from line phase-shift angle."""

    controlled_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "In the case of transformer type circuits with automatic tap variation, "
                "this field is for the number of the bus whose voltage magnitude should "
                "be controlled."
            ),
        ),
    ] = 'From Bus'
    dlin_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    emergency_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under emergency conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 'Normal Capacity'
    equipment_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Loading capacity of the equipment with the smallest loading capacity "
                "connected to the circuit."
            ),
        ),
    ] = 'Normal Capacity'
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at one end of the circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    from_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'
    normal_capacity: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit loading capacity under normal conditions for flow monitoring "
                "purposes, in MVA."
            ),
            json_schema_extra={"units": "MVA"},
        ),
    ] = 99999.0
    number_of_taps: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of positions of the variable tap transformer, including the "
                "minimum tap and maximum tap."
            ),
        ),
    ] = 33
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - Circuit data addition.\\nE or 1 - Circuit data elimination.\\nM "
                "or 2 - Circuit data modification."
            ),
        ),
    ] = 'A'
    owner: Annotated[
        ParsedScalar,
        Field(
            description=(
                "F if the circuit belongs to the area of the bus defined in the From Bus "
                "field.\\nT if the circuit belongs to the area of the bus defined in the "
                "To Bus field."
            ),
        ),
    ] = 'F'
    phase_shift: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Phase shift angle value, in degrees, for phase shifting transformers. "
                "The specified angular phase shift is applied relative to the angle of "
                "the bus defined in the From Bus field. Implicit decimal point between "
                "columns 56 and 57."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    reactance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit reactance value, in %. For transformers this value corresponds "
                "to the reactance value for the nominal tap. Implicit decimal point "
                "between columns 30 and 31."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    resistance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Circuit resistance value, in %. For transformers this value corresponds "
                "to the resistance value for the nominal tap. Implicit decimal point "
                "between columns 24 and 25."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 0.0
    state: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the circuit is in operation (connected).\\nD if the circuit is out "
                "of operation (disconnected)."
            ),
        ),
    ] = 'L'
    susceptance: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Total shunt susceptance value of the circuit, in Mvar. Implicit decimal "
                "point between columns 35 and 36."
            ),
        ),
    ] = 0.0
    tap: Annotated[
        ParsedScalar,
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
        ParsedScalar,
        Field(
            description=(
                "Maximum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 50 and 51."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    tap_minimum: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Minimum value that the tap can assume, in p.u., for automatic tap "
                "changing transformers. Implicit decimal point between columns 45 and 46."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    to_bus_opening: Annotated[
        ParsedScalar,
        Field(
            description="L - Connected.\\nD - Disconnected",
        ),
    ] = 'L'

class ShuntLine(AnaredeComponent):
    """Shunt line model."""

    dshl_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at one end of the AC circuit as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A or 0 - addition of AC circuit shunt device data.\\nE or 1 - elimination "
                "of AC circuit shunt device data.\\nM or 2 - modification of AC circuit "
                "shunt device data."
            ),
        ),
    ] = 'A'
    shunt_from: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Reactive power of shunts at the end defined in the From Bus field for "
                "nominal voltage (1.0 p.u.), in MVAr."
            ),
        ),
    ] = 0.0
    shunt_to: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Reactive power of shunts at the end defined in the To Bus field for "
                "nominal voltage (1.0 p.u.), in MVAr."
            ),
        ),
    ] = 0.0
    state_from: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the line shunt at this end is in operation (connected).\\nD if the "
                "line shunt at this end is out of operation (disconnected)."
            ),
        ),
    ] = 'L'
    state_to: Annotated[
        ParsedScalar,
        Field(
            description=(
                "L if the line shunt at this end is in operation (connected).\\nD if the "
                "line shunt at this end is out of operation (disconnected)."
            ),
        ),
    ] = 'L'
    to_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the bus at the other end of the circuit as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None

class DCLink(AnaredeComponent):
    """DC link model."""

    capacity: Annotated[
        ParsedScalar,
        Field(
            description="DC line loading capacity, in MW, for flow monitoring purposes.",
            json_schema_extra={"units": "MW"},
        ),
    ] = 0.0
    dcli_circuit: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the parallel DC line.",
        ),
    ] = None
    from_bus: Annotated[
        ParsedScalar,
        Field(
            description=(
                "Number of the DC bus at one end of the DC line, as defined in the Number "
                "field of the DCBA execution code."
            ),
        ),
    ] = None
    inductance: Annotated[
        ParsedScalar,
        Field(
            description="DC line inductance, in mH.",
            json_schema_extra={"units": "mH"},
        ),
    ] = 0.0
    operation: Annotated[
        ParsedScalar,
        Field(
            description="A or 0 - DC line data addition. M or 2 - DC line data modification.",
        ),
    ] = 'A'
    owner: Annotated[
        ParsedScalar,
        Field(
            description="Owner flag. This field is not used in this version.",
        ),
    ] = None
    resistance: Annotated[
        ParsedScalar,
        Field(
            description="DC line resistance, in ohms.",
            json_schema_extra={"units": "ohm"},
        ),
    ] = None
    to_bus: Annotated[
        ParsedScalar,
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
        ParsedScalar,
        Field(
            description="Identification number of the first selected parallel AC circuit.",
        ),
    ] = None
    circuit_2: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the second selected parallel AC circuit.",
        ),
    ] = None
    circuit_3: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the third selected parallel AC circuit.",
        ),
    ] = None
    circuit_4: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the fourth selected parallel AC circuit.",
        ),
    ] = None
    circuit_5: Annotated[
        ParsedScalar,
        Field(
            description="Identification number of the fifth selected parallel AC circuit.",
        ),
    ] = None
    from_bus_1: Annotated[
        ParsedScalar,
        Field(
            description="From bus of the first selected circuit.",
        ),
    ] = None
    from_bus_2: Annotated[
        ParsedScalar,
        Field(
            description="From bus of the second selected circuit.",
        ),
    ] = None
    from_bus_3: Annotated[
        ParsedScalar,
        Field(
            description="From bus of the third selected circuit.",
        ),
    ] = None
    from_bus_4: Annotated[
        ParsedScalar,
        Field(
            description="From bus of the fourth selected circuit.",
        ),
    ] = None
    from_bus_5: Annotated[
        ParsedScalar,
        Field(
            description="From bus of the fifth selected circuit.",
        ),
    ] = None
    operation: Annotated[
        ParsedScalar,
        Field(
            description=(
                "A - addition of fixed CTAP-control data. E - elimination of fixed "
                "CTAP-control data."
            ),
        ),
    ] = 'A'
    to_bus_1: Annotated[
        ParsedScalar,
        Field(
            description="To bus of the first selected circuit.",
        ),
    ] = None
    to_bus_2: Annotated[
        ParsedScalar,
        Field(
            description="To bus of the second selected circuit.",
        ),
    ] = None
    to_bus_3: Annotated[
        ParsedScalar,
        Field(
            description="To bus of the third selected circuit.",
        ),
    ] = None
    to_bus_4: Annotated[
        ParsedScalar,
        Field(
            description="To bus of the fourth selected circuit.",
        ),
    ] = None
    to_bus_5: Annotated[
        ParsedScalar,
        Field(
            description="To bus of the fifth selected circuit.",
        ),
    ] = None
