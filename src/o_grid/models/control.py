"""Control, options, and converter models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models.base import AnaredeComponent


class PowerFlowOption(AnaredeComponent):
    """Power flow option row."""

    option: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Power-flow execution option mnemonic. Examples include QLIM, CREM, STEP, "
                "NEWT, MOST, MOSG, MOSF, RCVG, RMON, FILE, CONT, CELO and MFCT."
            ),
        ),
    ] = None
    state: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Option activation state. L indicates that the execution option is enabled."
            ),
        ),
    ] = "L"


class ProgramConstant(AnaredeComponent):
    """Program constant row."""

    mnemonic: Annotated[
        int | float | str | None,
        Field(
            description="Constant mnemonic to be modified before execution of codes that use it.",
        ),
    ] = None
    value: Annotated[
        int | float | str | None,
        Field(
            description="New value associated with the DCTE constant mnemonic.",
        ),
    ] = 0.0


class TapTransformerControl(AnaredeComponent):
    """Control data for automatic tap-changing transformers (DCTR)."""

    curve_id: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identifier of the point-curve data associated with the complementary "
                "transformer record, when provided."
            ),
        ),
    ] = None
    dctr_circuit: Annotated[
        int | float | str | None,
        Field(
            description="Identification number of the parallel AC circuit.",
        ),
    ] = None
    from_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of one terminal bus of the circuit, as defined in the Number "
                "field of the DBAR Execution Code."
            ),
        ),
    ] = None
    maximum_phase_shift: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum phase-angle value, in degrees. Implicit decimal point between "
                "columns 43 and 44."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = None
    maximum_voltage: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum voltage magnitude of the controlled bus, in p.u. Implicit "
                "decimal point between columns 23 and 24."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    measurement_terminal: Annotated[
        int | float | str | None,
        Field(
            description="Bus where the control variable is measured.",
        ),
    ] = "From Bus"
    minimum_phase_shift: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum phase-angle value, in degrees. Implicit decimal point between "
                "columns 36 and 37."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = None
    minimum_voltage: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum voltage magnitude of the controlled bus, in p.u. Implicit "
                "decimal point between columns 18 and 19."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = None
    number_of_taps: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of phase-shifting transformer tap positions, including minimum "
                "and maximum taps. Not implemented in this ANAREDE version according to "
                "the manual."
            ),
        ),
    ] = 99
    operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "A or 0 - addition of complementary transformer data. E or 1 - "
                "elimination of complementary transformer data. M or 2 - modification of "
                "complementary transformer data."
            ),
        ),
    ] = "A"
    phase_control_type: Annotated[
        int | float | str | None,
        Field(
            description="F - Fixed. C - Current control. P - Active-power control.",
        ),
    ] = "F"
    phase_mode: Annotated[
        int | float | str | None,
        Field(
            description="C - Continuous phase control. D - Discrete phase control.",
        ),
    ] = "C"
    specified_value: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Specified current when Phase Control Type is C, in p.u.; or specified "
                "active power when Phase Control Type is P, in MW."
            ),
        ),
    ] = None
    to_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of the other terminal bus of the circuit, as defined in the "
                "Number field of the DBAR Execution Code."
            ),
        ),
    ] = None
    voltage_control_type: Annotated[
        int | float | str | None,
        Field(
            description="C - Center of voltage band. L - Voltage band limits.",
        ),
    ] = "C"


class ConverterControl(AnaredeComponent):
    """Converter control settings model."""

    converter_angle: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Desired firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    converter_control_type: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Converter control type: C for constant-current control, or P for "
                "constant-power control."
            ),
        ),
    ] = None
    current_margin: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Inverter current margin, in percent of the nominal current defined in "
                "the DCNV Current field. This field is not considered for rectifiers."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 10.0
    dc_voltage_minimum_for_power_control: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum DC voltage, in p.u., below which a converter in power control "
                "changes to current control. Implicit decimal point between columns 63 "
                "and 64."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = 0.0
    inverter_control_mode: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Inverter control mode for CCC inverters: G for gamma control, or T for "
                "AC interface bus voltage control."
            ),
        ),
    ] = None
    maximum_converter_angle: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    maximum_overcurrent: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Maximum overcurrent allowed for the converter, in percent of the nominal "
                "current defined in the DCNV Current field. This field is not considered "
                "for rectifiers."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = 9999.0
    maximum_transformer_tap: Annotated[
        int | float | str | None,
        Field(
            description="Maximum tap value of the converter transformer.",
        ),
    ] = None
    minimum_converter_angle: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Minimum firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = 0.0
    minimum_transformer_tap: Annotated[
        int | float | str | None,
        Field(
            description="Minimum tap value of the converter transformer.",
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Converter identification number, as defined in the Number field of the "
                "DCNV execution code."
            ),
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description=(
                "A or 0 - converter control data addition. E or 1 - converter control "
                "data elimination. M or 2 - converter control data modification."
            ),
        ),
    ] = "A"
    slack: Annotated[
        int | float | str | None,
        Field(
            description=(
                "F for a slack converter, or N for a normal converter. One slack "
                "converter must be specified for each pole of the DC link."
            ),
        ),
    ] = "N"
    specified_value: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Specified converter control value, in A for current control or MW for "
                "power control."
            ),
            json_schema_extra={"units": "A"},
        ),
    ] = None
    tap_himvar_mode: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Converter transformer tap used when the DC link operates in HiMVAr "
                "Consumption mode, as defined in the DELO HiMVAr Mode field."
            ),
        ),
    ] = None
    tap_reduced_voltage_mode: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Converter transformer tap used when the DC link operates in reduced-voltage mode."
            ),
        ),
    ] = "Maximum transformer tap minus one step, or 1.0 when the tap step is not available"
    transformer_tap_steps: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Number of converter transformer tap steps. The tap step is calculated by "
                "dividing the difference between maximum and minimum transformer taps by "
                "this number of steps."
            ),
        ),
    ] = "Infinity"


class ConverterStation(AnaredeComponent):
    """Converter station model."""

    ac_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "AC bus number to which the converter is connected, as defined in the "
                "Number field of the DBAR execution code."
            ),
        ),
    ] = None
    ccc_capacitance: Annotated[
        int | float | str | None,
        Field(
            description="CCC capacitance, in microfarads.",
            json_schema_extra={"units": "microfarad"},
        ),
    ] = 0.0
    commutation_reactance: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Commutation reactance per six-pulse bridge, in percent on the converter "
                "transformer power base."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = None
    current: Annotated[
        int | float | str | None,
        Field(
            description="Nominal converter current, in A.",
            json_schema_extra={"units": "A"},
        ),
    ] = None
    dc_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "DC bus number to which the converter is connected, as defined in the "
                "Number field of the DCBA execution code."
            ),
        ),
    ] = None
    frequency: Annotated[
        int | float | str | None,
        Field(
            description="Frequency, in Hz, of the AC system to which the CCC is connected.",
            json_schema_extra={"units": "Hz"},
        ),
    ] = 60
    mode: Annotated[
        int | float | str | None,
        Field(
            description="Converter operating mode: R for rectifier, or I for inverter.",
        ),
    ] = None
    neutral_bus: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Neutral DC bus number to which the converter is connected, as defined in "
                "the Number field of the DCBA execution code."
            ),
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description="Converter identification number.",
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description="A or 0 - converter data addition. M or 2 - converter data modification.",
        ),
    ] = "A"
    reactor_inductance: Annotated[
        int | float | str | None,
        Field(
            description="Smoothing reactor inductance, in mH.",
            json_schema_extra={"units": "mH"},
        ),
    ] = 0.0
    reactor_resistance: Annotated[
        int | float | str | None,
        Field(
            description="Smoothing reactor resistance, in ohms.",
            json_schema_extra={"units": "ohm"},
        ),
    ] = None
    secondary_voltage: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Line-to-line base voltage of the secondary side of the six-pulse bridge "
                "converter transformer, in kV."
            ),
            json_schema_extra={"units": "kV"},
        ),
    ] = None
    six_pulse_bridges: Annotated[
        int | float | str | None,
        Field(
            description="Number of six-pulse converter bridges.",
        ),
    ] = None
    transformer_power: Annotated[
        int | float | str | None,
        Field(
            description="Power base of the six-pulse bridge converter transformer, in MVA.",
            json_schema_extra={"units": "MVA"},
        ),
    ] = None


class TransferFunctionConstraint(AnaredeComponent):
    """Transfer-function constraint model."""

    condition_1: Annotated[
        int | float | str | None,
        Field(
            description=(
                "First condition operator. A specifies an interval condition. E specifies "
                "a union condition."
            ),
        ),
    ] = None
    condition_2: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Second condition operator. A specifies an interval condition. E "
                "specifies a union condition."
            ),
        ),
    ] = None
    element_id_1: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identifier of the first element: bus number, area number, voltage base, "
                "or aggregator identifier."
            ),
        ),
    ] = None
    element_id_2: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identifier of the second element: bus number, area number, voltage base, "
                "or aggregator identifier."
            ),
        ),
    ] = None
    element_id_3: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identifier of the third element: bus number, area number, voltage base, "
                "or aggregator identifier."
            ),
        ),
    ] = None
    element_id_4: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Identifier of the fourth element: bus number, area number, voltage base, "
                "or aggregator identifier."
            ),
        ),
    ] = None
    element_type_1: Annotated[
        int | float | str | None,
        Field(
            description=(
                "First element type. BARR specifies a bus, AREA an area, TENS a voltage "
                "base, and AG01 through AG10 an aggregator."
            ),
        ),
    ] = None
    element_type_2: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Second element type. BARR specifies a bus, AREA an area, TENS a voltage "
                "base, and AG01 through AG10 an aggregator."
            ),
        ),
    ] = None
    element_type_3: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Third element type. BARR specifies a bus, AREA an area, TENS a voltage "
                "base, and AG01 through AG10 an aggregator."
            ),
        ),
    ] = None
    element_type_4: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Fourth element type. BARR specifies a bus, AREA an area, TENS a voltage "
                "base, and AG01 through AG10 an aggregator."
            ),
        ),
    ] = None
    interconnection: Annotated[
        int | float | str | None,
        Field(
            description=(
                "T fixes automatic tap voltage control for all selected transformers. I "
                "fixes only selected interconnection circuits."
            ),
        ),
    ] = "T"
    main_condition: Annotated[
        int | float | str | None,
        Field(
            description=(
                "Main condition between the sets defined by conditions 1 and 2. X means "
                "difference, E union, and S intersection."
            ),
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


class DCLinkOwner(AnaredeComponent):
    """DC link owner model."""

    himvar_mode: Annotated[
        int | float | str | None,
        Field(
            description=(
                "DC link operating mode selector: N for normal operation, or H for HiMVAr "
                "Consumption mode."
            ),
        ),
    ] = "N"
    anarede_name: Annotated[
        int | float | str | None,
        Field(
            description="Alphanumeric identification of the DC link name.",
        ),
    ] = None
    number: Annotated[
        int | float | str | None,
        Field(
            description="DC link identification number.",
        ),
    ] = None
    operation: Annotated[
        int | float | str | None,
        Field(
            description="A or 0 - DC link data addition. M or 2 - DC link data modification.",
        ),
    ] = "A"
    power_base: Annotated[
        int | float | str | None,
        Field(
            description="DC link power base, in MW.",
            json_schema_extra={"units": "MW"},
        ),
    ] = "DASE constant base"
    state: Annotated[
        int | float | str | None,
        Field(
            description="L if the DC link is in operation. D if the DC link is out of operation.",
        ),
    ] = "L"
    voltage: Annotated[
        int | float | str | None,
        Field(
            description="Nominal DC link operating voltage, in kV.",
            json_schema_extra={"units": "kV"},
        ),
    ] = None
