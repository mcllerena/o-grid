"""Network formulation registry used by ACOPF solvers.

The formulation classes mirror the public ACOPF formulation names. Concrete
Pyomo builders are added per formulation family; the registry prevents a
solver from silently substituting one formulation for another.
"""

from o_grid.acopf.formulations import (
    FORMULATION_REGISTRY,
    ACPPowerModel,
    ACRPowerModel,
    ACTPowerModel,
    BFAPowerModel,
    DCMPPowerModel,
    DCPLLPowerModel,
    DCPPowerModel,
    IVRPowerModel,
    LPACCPowerModel,
    NFAPowerModel,
    PowerModelFormulation,
    QCLSPowerModel,
    QCRMPowerModel,
    SDPWRMPowerModel,
    SOCBFConicPowerModel,
    SOCBFPowerModel,
    SOCWRConicPowerModel,
    SOCWRPowerModel,
    SparseSDPWRMPowerModel,
    implemented_formulations,
    resolve_formulation,
)

__all__ = [
    "ACPPowerModel",
    "ACRPowerModel",
    "ACTPowerModel",
    "BFAPowerModel",
    "DCPPowerModel",
    "DCMPPowerModel",
    "DCPLLPowerModel",
    "FORMULATION_REGISTRY",
    "IVRPowerModel",
    "LPACCPowerModel",
    "NFAPowerModel",
    "PowerModelFormulation",
    "QCLSPowerModel",
    "QCRMPowerModel",
    "SDPWRMPowerModel",
    "SOCBFConicPowerModel",
    "SOCBFPowerModel",
    "SOCWRConicPowerModel",
    "SOCWRPowerModel",
    "SparseSDPWRMPowerModel",
    "implemented_formulations",
    "resolve_formulation",
]
