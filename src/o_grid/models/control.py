"""Control, options, and converter models."""

from __future__ import annotations

import math
from typing import Annotated

from infrasys import Component
from pydantic import Field, field_validator, model_validator

from o_grid.models.base import AnaredeComponent
from o_grid.models.enums import (
    CircuitState,
    ConverterControlSlack,
    ConverterControlType,
    ConverterMode,
    HighVArMode,
    InverterControlMode,
    OptionState,
)
from o_grid.models.topology import ACBus, DCBus
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
    get_magnitude,
)

PROGRAM_CONSTANT_DEFAULTS: dict[str, int | float] = {
    "TEPA": 0.1,
    "TEPR": 0.1,
    "TLPR": 0.1,
    "TLVC": 0.5,
    "TLTC": 0.01,
    "TETP": 5.0,
    "TBPA": 5.0,
    "TSFR": 0.01,
    "TUDC": 0.001,
    "TADC": 0.01,
    "BASE": 100.0,
    "DASE": 100.0,
    "ZMAX": 500.0,
    "ACIT": 30,
    "LPIT": 50,
    "LFLP": 10,
    "LFIT": 10,
    "DCIT": 10,
    "VSIT": 10,
    "LCRT": 23,
    "LPRT": 60,
    "LFCV": 1,
    "TPST": 0.2,
    "QLST": 0.4,
    "EXST": 0.4,
    "TLPP": 1.0,
    "TSBZ": 0.01,
    "TSBA": 5.0,
    "PGER": 30.0,
    "VDVN": 40.0,
    "VDVM": 200.0,
    "ASTP": 0.05,
    "VSTP": 5.0,
    "CSTP": 5.0,
    "VFLD": 70.0,
    "ZMIN": 0.001,
    "PDIT": 10,
    "ICIT": 30,
    "FDIV": 2.0,
    "DMAX": 5,
    "ICMN": 0.05,
    "VART": 5.0,
    "TSTP": 33,
    "ICMV": 0.5,
    "APAS": 90.0,
    "CPAR": 70.0,
    "VAVT": 2.0,
    "VAVF": 5.0,
    "VMVF": 15.0,
    "VPVT": 2.0,
    "VPVF": 5.0,
    "VPMF": 10.0,
    "VSVF": 20.0,
    "VINF": 1.0,
    "VSUP": 1.0,
    "TSDC": 0.02,
    "ASDC": 1.0,
    "TLSI": 0.0,
    "NDIR": 20,
    "STIR": 1,
    "STTR": 5.0,
    "TRPT": 100.0,
    "BFPO": 1.0,
    "LFPO": 0.1,
    "TLMT": 0.0,
    "TLMF": 0.0,
    "TLMG": 0.0,
    "PARS": 10.0,
}

PROGRAM_CONSTANT_UNITS: dict[str, tuple[type, str]] = {
    "TEPA": (ActivePower, "MW"),
    "TETP": (ActivePower, "MW"),
    "TBPA": (ActivePower, "MW"),
    "TSBZ": (ActivePower, "MW"),
    "TSBA": (ActivePower, "MW"),
    "VMVF": (ActivePower, "MW"),
    "VPMF": (ActivePower, "MW"),
    "DASE": (ActivePower, "MW"),
    "TEPR": (ReactivePower, "MVAr"),
    "TLPR": (ReactivePower, "MVAr"),
    "BFPO": (ReactivePower, "MVAr"),
    "BASE": (ApparentPower, "MVA"),
    "TLVC": (Percentage, "%"),
    "TLTC": (Percentage, "%"),
    "TSFR": (Percentage, "%"),
    "TUDC": (Percentage, "%"),
    "TADC": (Percentage, "%"),
    "ZMAX": (Percentage, "%"),
    "TLPP": (Percentage, "%"),
    "PGER": (Percentage, "%"),
    "VDVN": (Percentage, "%"),
    "VDVM": (Percentage, "%"),
    "VSTP": (Percentage, "%"),
    "CSTP": (Percentage, "%"),
    "VFLD": (Percentage, "%"),
    "ZMIN": (Percentage, "%"),
    "ICMN": (Percentage, "%"),
    "VART": (Percentage, "%"),
    "ICMV": (Percentage, "%"),
    "APAS": (Percentage, "%"),
    "CPAR": (Percentage, "%"),
    "VAVT": (Percentage, "%"),
    "VAVF": (Percentage, "%"),
    "VPVT": (Percentage, "%"),
    "VPVF": (Percentage, "%"),
    "VSVF": (Percentage, "%"),
    "STTR": (Percentage, "%"),
    "TRPT": (Percentage, "%"),
    "TLMT": (Percentage, "%"),
    "TLMF": (Percentage, "%"),
    "TLMG": (Percentage, "%"),
    "PARS": (Percentage, "%"),
    "ASTP": (Angle, "radian"),
    "ASDC": (Angle, "degree"),
    "LFPO": (ActivePower, "MW"),
}


class PowerFlowOption(Component):
    """Power flow option row."""

    option: Annotated[
        str | None,
        Field(
            description=(
                "Power-flow execution option mnemonic. Examples include QLIM, CREM, STEP, "
                "NEWT, MOST, MOSG, MOSF, RCVG, RMON, FILE, CONT, CELO and MFCT."
            ),
        ),
    ] = None
    state: Annotated[
        OptionState,
        Field(
            description=(
                "Option activation state. L indicates that the execution option is enabled."
            ),
        ),
    ] = OptionState.ACTIVATED


class ProgramConstant(Component):
    """Program constant row."""

    mnemonic: Annotated[
        str | None,
        Field(
            description="Constant mnemonic to be modified before execution of codes that use it.",
        ),
    ] = None
    value: Annotated[
        ActivePower | ReactivePower | ApparentPower | Percentage | Angle | int | float | None,
        Field(
            description="New value associated with the DCTE constant mnemonic.",
        ),
    ] = 0.0

    @model_validator(mode="after")
    def _apply_defaults_and_units(self) -> ProgramConstant:
        mnemonic = (self.mnemonic or "").strip().upper()
        object.__setattr__(self, "mnemonic", mnemonic or None)

        value = self.value
        if value is None and mnemonic in PROGRAM_CONSTANT_DEFAULTS:
            value = PROGRAM_CONSTANT_DEFAULTS[mnemonic]
        if isinstance(value, str):
            stripped = value.strip()
            value = float(stripped) if stripped else None

        unit_spec = PROGRAM_CONSTANT_UNITS.get(mnemonic)
        if unit_spec is None:
            object.__setattr__(self, "value", value)
            return self

        quantity_type, unit_name = unit_spec
        if value is None:
            object.__setattr__(self, "value", None)
            return self

        magnitude = get_magnitude(value)
        object.__setattr__(self, "value", quantity_type(float(magnitude), unit_name))
        return self


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
        Angle | None,
        Field(
            description=(
                "Desired firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = Angle(0.0, "degree")
    converter_control_type: Annotated[
        ConverterControlType | None,
        Field(
            description=(
                "Converter control type: C for constant-current control, or P for "
                "constant-power control."
            ),
        ),
    ] = None
    current_margin: Annotated[
        Percentage | None,
        Field(
            description=(
                "Inverter current margin, in percent of the nominal current defined in "
                "the DCNV Current field. This field is not considered for rectifiers."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(10.0, "%")
    dc_voltage_minimum_for_power_control: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Minimum DC voltage, in p.u., below which a converter in power control "
                "changes to current control. Implicit decimal point between columns 63 "
                "and 64."
            ),
            json_schema_extra={"units": "p.u."},
        ),
    ] = PerUnit(0.0, "pu")
    inverter_control_mode: Annotated[
        InverterControlMode | None,
        Field(
            description=(
                "Inverter control mode for CCC inverters: G for gamma control, or T for "
                "AC interface bus voltage control."
            ),
        ),
    ] = InverterControlMode.GAMMA_CONTROLLED
    maximum_converter_angle: Annotated[
        Angle | None,
        Field(
            description=(
                "Maximum firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = Angle(0.0, "degree")
    maximum_overcurrent: Annotated[
        Percentage | None,
        Field(
            description=(
                "Maximum overcurrent allowed for the converter, in percent of the nominal "
                "current defined in the DCNV Current field. This field is not considered "
                "for rectifiers."
            ),
            json_schema_extra={"units": "%"},
        ),
    ] = Percentage(9999.0, "%")
    maximum_transformer_tap: Annotated[
        PerUnit | None,
        Field(
            description="Maximum tap value of the converter transformer.",
        ),
    ] = None
    minimum_converter_angle: Annotated[
        Angle | None,
        Field(
            description=(
                "Minimum firing angle for a rectifier, extinction angle for a "
                "conventional inverter, or commutation margin for a CCC inverter, in "
                "degrees."
            ),
            json_schema_extra={"units": "degrees"},
        ),
    ] = Angle(0.0, "degree")
    minimum_transformer_tap: Annotated[
        PerUnit | None,
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
    slack: Annotated[
        ConverterControlSlack | None,
        Field(
            description=(
                "F for a slack converter, or N for a normal converter. One slack "
                "converter must be specified for each pole of the DC link."
            ),
        ),
    ] = ConverterControlSlack.NORMAL
    specified_value: Annotated[
        ActivePower | Current | float | None,
        Field(
            description=(
                "Specified converter control value, in A for current control or MW for "
                "power control."
            ),
            json_schema_extra={"units": "A|MW"},
        ),
    ] = None
    tap_himvar_mode: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Converter transformer tap used when the DC link operates in HiMVAr "
                "Consumption mode, as defined in the DELO HiMVAr Mode field."
            ),
        ),
    ] = None
    tap_reduced_voltage_mode: Annotated[
        PerUnit | None,
        Field(
            description=(
                "Converter transformer tap used when the DC link operates in reduced-voltage mode."
            ),
        ),
    ] = PerUnit(1.0, "pu")
    transformer_tap_steps: Annotated[
        int | float | None,
        Field(
            description=(
                "Number of converter transformer tap steps. The tap step is calculated by "
                "dividing the difference between maximum and minimum transformer taps by "
                "this number of steps."
            ),
        ),
    ] = math.inf

    @field_validator("converter_control_type", mode="before")
    @classmethod
    def _coerce_converter_control_type(cls, value: object) -> ConverterControlType | None:
        if value is None:
            return None
        if isinstance(value, ConverterControlType):
            return value
        text = str(value).strip().upper()
        if text == ConverterControlType.CURRENT.value:
            return ConverterControlType.CURRENT
        if text == ConverterControlType.POWER.value:
            return ConverterControlType.POWER
        return None

    @field_validator("slack", mode="before")
    @classmethod
    def _coerce_slack(cls, value: object) -> ConverterControlSlack | None:
        if value is None:
            return ConverterControlSlack.NORMAL
        if isinstance(value, ConverterControlSlack):
            return value
        text = str(value).strip().upper()
        if text == ConverterControlSlack.SLACK.value:
            return ConverterControlSlack.SLACK
        if text == ConverterControlSlack.NORMAL.value:
            return ConverterControlSlack.NORMAL
        return ConverterControlSlack.NORMAL

    @field_validator("inverter_control_mode", mode="before")
    @classmethod
    def _coerce_inverter_control_mode(cls, value: object) -> InverterControlMode | None:
        if value is None:
            return None
        if isinstance(value, InverterControlMode):
            return value
        text = str(value).strip().upper()
        if text == InverterControlMode.GAMMA_CONTROLLED.value:
            return InverterControlMode.GAMMA_CONTROLLED
        if text == InverterControlMode.ACBUS_CONTROLLED.value:
            return InverterControlMode.ACBUS_CONTROLLED
        return None

    @staticmethod
    def _numeric_or_none(value: object) -> float | None:
        if value is None:
            return None
        magnitude = get_magnitude(value)
        if isinstance(magnitude, (int, float)):
            return float(magnitude)
        text = str(magnitude).strip()
        if not text:
            return None
        if text.lower() in {"inf", "infinity", "∞"}:
            return math.inf
        try:
            return float(text)
        except ValueError:
            return None

    @model_validator(mode="after")
    def _coerce_enums_and_units(self) -> ConverterControl:
        control_type = self.converter_control_type

        for field_name in ("converter_angle", "minimum_converter_angle", "maximum_converter_angle"):
            value = self._numeric_or_none(getattr(self, field_name))
            if value is not None and not math.isinf(value):
                object.__setattr__(self, field_name, Angle(value, "degree"))

        for field_name in ("current_margin", "maximum_overcurrent"):
            value = self._numeric_or_none(getattr(self, field_name))
            if value is not None and not math.isinf(value):
                object.__setattr__(self, field_name, Percentage(value, "%"))

        for field_name in (
            "dc_voltage_minimum_for_power_control",
            "minimum_transformer_tap",
            "maximum_transformer_tap",
            "tap_himvar_mode",
            "tap_reduced_voltage_mode",
        ):
            value = self._numeric_or_none(getattr(self, field_name))
            if value is not None and not math.isinf(value):
                object.__setattr__(self, field_name, PerUnit(value, "pu"))

        specified = self._numeric_or_none(self.specified_value)
        if specified is not None and not math.isinf(specified):
            if control_type == ConverterControlType.POWER:
                object.__setattr__(self, "specified_value", ActivePower(specified, "MW"))
            elif control_type == ConverterControlType.CURRENT:
                object.__setattr__(self, "specified_value", Current(specified, "A"))
            else:
                object.__setattr__(self, "specified_value", specified)

        tap_steps = self.transformer_tap_steps
        if tap_steps is None:
            object.__setattr__(self, "transformer_tap_steps", math.inf)
        else:
            tap_steps_value = self._numeric_or_none(tap_steps)
            if tap_steps_value is None or math.isinf(tap_steps_value):
                object.__setattr__(self, "transformer_tap_steps", math.inf)
            else:
                object.__setattr__(
                    self,
                    "transformer_tap_steps",
                    int(tap_steps_value)
                    if float(tap_steps_value).is_integer()
                    else tap_steps_value,
                )

        return self


class ConverterStation(AnaredeComponent):
    """Converter station model."""

    ac_bus: Annotated[
        ACBus | int | float | str | None,
        Field(
            description=(
                "AC bus to which the converter is connected, as defined in the "
                "Number field of the DBAR execution code."
            ),
        ),
    ] = None
    ccc_capacitance: Annotated[
        Capacitance | None,
        Field(
            description="CCC capacitance, in microfarads.",
        ),
    ] = Capacitance(0.0, "microfarad")
    commutation_reactance: Annotated[
        Percentage | None,
        Field(
            description=(
                "Commutation reactance per six-pulse bridge, in percent on the converter "
                "transformer power base."
            ),
        ),
    ] = None
    current: Annotated[
        Current | None,
        Field(
            description="Nominal converter current, in A.",
        ),
    ] = None
    dc_bus: Annotated[
        DCBus | int | float | str | None,
        Field(
            description=(
                "DC bus to which the converter is connected, as defined in the "
                "Number field of the DCBA execution code."
            ),
        ),
    ] = None
    frequency: Annotated[
        Frequency | None,
        Field(
            description="Frequency, in Hz, of the AC system to which the CCC is connected.",
        ),
    ] = Frequency(60, "hertz")
    mode: Annotated[
        ConverterMode | None,
        Field(
            description="Converter operating mode: R for rectifier, or I for inverter.",
        ),
    ] = None
    neutral_bus: Annotated[
        DCBus | int | float | str | None,
        Field(
            description=(
                "Neutral DC bus to which the converter is connected, as defined in "
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
    reactor_inductance: Annotated[
        Inductance | None,
        Field(
            description="Smoothing reactor inductance, in mH.",
        ),
    ] = Inductance(0.0, "millihenry")
    reactor_resistance: Annotated[
        Resistance | None,
        Field(
            description="Smoothing reactor resistance, in ohms.",
        ),
    ] = None
    secondary_voltage: Annotated[
        Voltage | None,
        Field(
            description=(
                "Line-to-line base voltage of the secondary side of the six-pulse bridge "
                "converter transformer, in kV."
            ),
        ),
    ] = None
    six_pulse_bridges: Annotated[
        int | float | str | None,
        Field(
            description="Number of six-pulse converter bridges.",
        ),
    ] = None
    transformer_power: Annotated[
        ApparentPower | None,
        Field(
            description="Power base of the six-pulse bridge converter transformer, in MVA.",
        ),
    ] = None

    @field_validator("mode", mode="before")
    @classmethod
    def _coerce_mode(cls, value: object) -> ConverterMode | None:
        if value is None:
            return None
        if isinstance(value, ConverterMode):
            return value
        text = str(value).strip().upper()
        if text == ConverterMode.RECTIFIER.value:
            return ConverterMode.RECTIFIER
        if text == ConverterMode.INVERTER.value:
            return ConverterMode.INVERTER
        return None


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


class DCLineData(AnaredeComponent):
    """DC link data model."""

    himvar_mode: Annotated[
        HighVArMode | None,
        Field(
            description=(
                "DC link operating mode selector: N for normal operation, or H for HiMVAr "
                "Consumption mode."
            ),
        ),
    ] = HighVArMode.NORMAL_MODE
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
    power_base: Annotated[
        ActivePower | None,
        Field(
            description="DC link power base, in MW. Defaults to the DASE program constant.",
            json_schema_extra={"units": "MW"},
        ),
    ] = None
    state: Annotated[
        CircuitState | None,
        Field(
            description="L if the DC link is in operation. D if the DC link is out of operation.",
        ),
    ] = CircuitState.CLOSED
    voltage: Annotated[
        Voltage | None,
        Field(
            description="Nominal DC link operating voltage, in kV.",
            json_schema_extra={"units": "kV"},
        ),
    ] = None
