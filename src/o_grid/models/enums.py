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


class SVCControlMode(StrEnum):
    """Enum defining SVC control modes."""

    POWER = "P"
    CURRENT = "I"


class CSCControlMode(StrEnum):
    """Enum defining CSC control modes."""

    POWER = "P"
    CURRENT = "I"
    REACTANCE = "X"


class CircuitState(StrEnum):
    """Enum defining circuit connected/disconnected states."""

    CLOSED = "L"
    OPEN = "D"


class OptionState(StrEnum):
    """Enum defining power-flow option activation states."""

    ACTIVATED = "L"
    DEACTIVATED = "D"
