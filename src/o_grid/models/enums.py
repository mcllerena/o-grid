"""Enumerations for o_grid model components."""

from __future__ import annotations

from enum import StrEnum


class ACBusTypes(StrEnum):
    """Enum defining AC bus categories."""

    PV = "PV"
    PQ = "PQ"
    REF = "REF"
    SLACK = "SLACK"
    ISOLATED = "ISOLATED"


class DCBusPolarity(StrEnum):
    """Enum defining DC bus polarity."""

    POSITIVE_POLE = "+"
    NEGATIVE_POLE = "-"
    NEUTRAL = "0"


class DCBusType(StrEnum):
    """Enum defining DC bus type."""

    NO_VOLTAGE = "0"
    REFERENCE = "1"


class ConverterControlType(StrEnum):
    """Enum defining DCCV converter control type."""

    CURRENT = "C"
    POWER = "P"


class ConverterControlSlack(StrEnum):
    """Enum defining DCCV slack-converter flag."""

    SLACK = "F"
    NORMAL = "N"


class InverterControlMode(StrEnum):
    """Enum defining DCCV inverter control mode for CCC inverters."""

    GAMMA_CONTROLLED = "G"
    ACBUS_CONTROLLED = "T"


class ConverterMode(StrEnum):
    """Enum defining DCNV converter operating mode."""

    RECTIFIER = "R"
    INVERTER = "I"


class SVCControlMode(StrEnum):
    """Enum defining SVC control modes."""

    POWER = "P"
    CURRENT = "I"


class CSCControlMode(StrEnum):
    """Enum defining CSC control modes."""

    POWER = "P"
    CURRENT = "I"
    REACTANCE = "X"


class ShuntControlMode(StrEnum):
    """Enum defining DBSH automatic switching control modes."""

    CONTINUOUS = "C"
    DISCRETE = "D"
    FIXED = "F"


class BankControllerControlType(StrEnum):
    """Enum defining DBSH bank controller voltage control types."""

    VOLTAGE_CONTROL_RANGE = "C"
    VOLTAGE_LIMIT_VIOLATION_RANGE = "L"


class CircuitState(StrEnum):
    """Enum defining circuit connected/disconnected states."""

    CLOSED = "L"
    OPEN = "D"


class HighVArMode(StrEnum):
    """Enum defining the DC link High MVAr operating mode."""

    NORMAL_MODE = "N"
    HIGH_VAR_MODE = "H"


class OptionState(StrEnum):
    """Enum defining power-flow option activation states."""

    ACTIVATED = "L"
    DEACTIVATED = "D"


class VoltageMonitoringCondition(StrEnum):
    """Enum defining selection-set operators for AC bus voltage monitoring (DMTE)."""

    INTERVAL = "A"
    UNION = "E"
    DIFFERENCE = "X"
    INTERSECTION = "S"


class TransformerManeuverable(StrEnum):
    """Enum defining whether a transformer is maneuverable (DLIN)."""

    MANEUVERABLE = "S"
    NON_MANEUVERABLE = "N"


class GenType(StrEnum):
    """Enum defining generator technology types from the gen-type mapping."""

    NUCLEAR = "Nuclear"
    HYDRO = "Hydro"
    PCH = "PCH"
    PV = "PV"
    STEAM = "Steam"
    SYNCHRONOUS_COMPENSATOR = "Synch.Comp."
    WIND = "Wind"
    UNKNOWN = "Unknown"
