"""Typed model exports and block-to-model registry."""

from __future__ import annotations

from o_grid.models.base import AnaredeComponent
from o_grid.models.branch import (
    ACLine,
    DCLink,
    PhaseShiftingTransformer,
    SeriesCompensator,
    ShuntLine,
    TapChangingTransformer,
    TransferFunctionCircuit,
)
from o_grid.models.buses import ACBus, ControlArea, DCBus, VoltageBaseGroup, VoltageLimitGroup
from o_grid.models.case import CaseTitle
from o_grid.models.control import (
    ConverterControl,
    ConverterStation,
    DCLinkOwner,
    PowerFlowOption,
    ProgramConstant,
    TapTransformerControl,
    TransferFunctionConstraint,
)
from o_grid.models.generators import GeneratorDispatchData, ReactiveCompensator
from o_grid.models.load import (
    BusShunt,
    CurrentInjectionLoad,
    LineShunt,
    ShuntBank,
    ShuntCompensator,
)

BLOCK_BASE_CLASSES: dict[str, type[AnaredeComponent]] = {
    "TITU": CaseTitle,
    "DOPC": PowerFlowOption,
    "DCTE": ProgramConstant,
    "DBAR": ACBus,
    "DLIN": ACLine,
    "DGLT": VoltageLimitGroup,
    "DGBT": VoltageBaseGroup,
    "DARE": ControlArea,
    "DBSH": BusShunt,
    "DBSH_BANK": LineShunt,
    "DCAI": CurrentInjectionLoad,
    "DCER": ReactiveCompensator,
    "DCSC": SeriesCompensator,
    "DCTR": TapTransformerControl,
    "DGER": GeneratorDispatchData,
    "DCLI": DCLink,
    "DCBA": DCBus,
    "DCCV": ConverterControl,
    "DCNV": ConverterStation,
    "DELO": DCLinkOwner,
    "DSHL": ShuntLine,
    "DTPF": TransferFunctionConstraint,
    "DTPF_CIRC": TransferFunctionCircuit,
    "DLIN_TAP": TapChangingTransformer,
    "DLIN_PHASE_SHIFT": PhaseShiftingTransformer,
}

__all__ = [
    "ACBus",
    "ACLine",
    "AnaredeComponent",
    "BLOCK_BASE_CLASSES",
    "BusShunt",
    "CaseTitle",
    "ControlArea",
    "ConverterControl",
    "ConverterStation",
    "CurrentInjectionLoad",
    "DCBus",
    "DCLink",
    "DCLinkOwner",
    "GeneratorDispatchData",
    "LineShunt",
    "PhaseShiftingTransformer",
    "PowerFlowOption",
    "ProgramConstant",
    "ReactiveCompensator",
    "SeriesCompensator",
    "ShuntBank",
    "ShuntCompensator",
    "ShuntLine",
    "TapTransformerControl",
    "TapChangingTransformer",
    "TransferFunctionCircuit",
    "TransferFunctionConstraint",
    "VoltageBaseGroup",
    "VoltageLimitGroup",
]
