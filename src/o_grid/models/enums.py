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