"""ACOPF formulation definitions and registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerModelFormulation:
    """Describe one network formulation exposed by the ACOPF API."""

    name: str
    family: str
    description: str
    implemented: bool = False


class ACPPowerModel(PowerModelFormulation):
    """Exact non-convex AC model with polar voltage variables."""

    def __init__(self) -> None:
        super().__init__(
            name="ACPPowerModel",
            family="exact_nonconvex",
            description="AC power-flow equations in polar voltage coordinates.",
            implemented=True,
        )


class ACRPowerModel(PowerModelFormulation):
    """Exact non-convex AC model with rectangular voltage variables."""

    def __init__(self) -> None:
        super().__init__(
            name="ACRPowerModel",
            family="exact_nonconvex",
            description="AC power-flow equations in rectangular voltage coordinates.",
            implemented=True,
        )


class ACTPowerModel(PowerModelFormulation):
    """Exact tangent-coordinate AC model."""

    def __init__(self) -> None:
        super().__init__(
            name="ACTPowerModel",
            family="exact_nonconvex",
            description="AC model using voltage squares, cross-products, and tangent constraints.",
            implemented=True,
        )


class IVRPowerModel(PowerModelFormulation):
    """Current-voltage rectangular AC model."""

    def __init__(self) -> None:
        super().__init__(
            name="IVRPowerModel",
            family="exact_nonconvex",
            description="Rectangular current-voltage formulation.",
            implemented=True,
        )


class DCPPowerModel(PowerModelFormulation):
    """Linear DC power-flow approximation."""

    def __init__(self) -> None:
        super().__init__(
            name="DCPPowerModel",
            family="linear_approximation",
            description="Basic linear active-power-only approximation.",
            implemented=True,
        )


class DCMPPowerModel(PowerModelFormulation):
    """Transformer-aware linear DC approximation."""

    def __init__(self) -> None:
        super().__init__(
            name="DCMPPowerModel",
            family="linear_approximation",
            description="Linear DC approximation with transformer parameters.",
            implemented=True,
        )


class BFAPowerModel(PowerModelFormulation):
    """Linear branch-flow approximation."""

    def __init__(self) -> None:
        super().__init__(
            name="BFAPowerModel",
            family="linear_approximation",
            description="Active-power branch-flow approximation.",
            implemented=True,
        )


class NFAPowerModel(PowerModelFormulation):
    """Linear network-flow approximation."""

    def __init__(self) -> None:
        super().__init__(
            name="NFAPowerModel",
            family="linear_approximation",
            description="Active-power transportation/network-flow approximation.",
            implemented=True,
        )


class DCPLLPowerModel(PowerModelFormulation):
    """Loss-approximated DC model."""

    def __init__(self) -> None:
        super().__init__(
            name="DCPLLPowerModel",
            family="quadratic_approximation",
            description="DC model with a linearized loss representation.",
        )


class LPACCPowerModel(PowerModelFormulation):
    """Linearized polar AC approximation."""

    def __init__(self) -> None:
        super().__init__(
            name="LPACCPowerModel",
            family="quadratic_approximation",
            description="Linearized polar AC approximation.",
        )


class SOCWRPowerModel(PowerModelFormulation):
    """Second-order cone relaxation in lifted rectangular variables."""

    def __init__(self) -> None:
        super().__init__(
            name="SOCWRPowerModel",
            family="quadratic_relaxation",
            description="Second-order cone relaxation in W-space.",
            implemented=True,
        )


class SOCWRConicPowerModel(SOCWRPowerModel):
    """Conic-solver variant of the W-space SOC relaxation."""

    def __init__(self) -> None:
        PowerModelFormulation.__init__(
            self,
            name="SOCWRConicPowerModel",
            family="quadratic_relaxation",
            description="Conic-solver W-space second-order cone relaxation.",
            implemented=True,
        )


class QCRMPowerModel(PowerModelFormulation):
    """Quadratic constraint relaxation."""

    def __init__(self) -> None:
        super().__init__(
            name="QCRMPowerModel",
            family="quadratic_relaxation",
            description="Quadratic constraint relaxation of AC power flow.",
        )


class QCLSPowerModel(PowerModelFormulation):
    """Quadratic constraint least-squares relaxation."""

    def __init__(self) -> None:
        super().__init__(
            name="QCLSPowerModel",
            family="quadratic_relaxation",
            description="Quadratic constraint least-squares relaxation.",
        )


class SOCBFPowerModel(PowerModelFormulation):
    """Second-order cone branch-flow relaxation."""

    def __init__(self) -> None:
        super().__init__(
            name="SOCBFPowerModel",
            family="quadratic_relaxation",
            description="Second-order cone branch-flow relaxation.",
            implemented=True,
        )


class SOCBFConicPowerModel(SOCBFPowerModel):
    """Conic-solver variant of the branch-flow SOC relaxation."""

    def __init__(self) -> None:
        PowerModelFormulation.__init__(
            self,
            name="SOCBFConicPowerModel",
            family="quadratic_relaxation",
            description="Conic-solver branch-flow second-order cone relaxation.",
            implemented=True,
        )


class SDPWRMPowerModel(PowerModelFormulation):
    """Semidefinite relaxation in lifted W-space."""

    def __init__(self) -> None:
        super().__init__(
            name="SDPWRMPowerModel",
            family="sdp_relaxation",
            description="Semidefinite relaxation in W-space.",
            implemented=True,
        )


class SparseSDPWRMPowerModel(SDPWRMPowerModel):
    """Sparse semidefinite W-space relaxation."""

    def __init__(self) -> None:
        PowerModelFormulation.__init__(
            self,
            name="SparseSDPWRMPowerModel",
            family="sdp_relaxation",
            description="Sparse semidefinite relaxation in W-space.",
            implemented=True,
        )


_FORMULATION_TYPES = (
    ACPPowerModel,
    ACRPowerModel,
    ACTPowerModel,
    IVRPowerModel,
    DCPPowerModel,
    DCMPPowerModel,
    BFAPowerModel,
    NFAPowerModel,
    DCPLLPowerModel,
    LPACCPowerModel,
    SOCWRPowerModel,
    SOCWRConicPowerModel,
    QCRMPowerModel,
    QCLSPowerModel,
    SOCBFPowerModel,
    SOCBFConicPowerModel,
    SDPWRMPowerModel,
    SparseSDPWRMPowerModel,
)

FORMULATION_REGISTRY = {formulation().name: formulation for formulation in _FORMULATION_TYPES}


def resolve_formulation(formulation: str) -> PowerModelFormulation:
    """Resolve an ACOPF formulation class name or short name to a formulation."""
    normalized = formulation.strip().lower()
    aliases = {
        "acp": "ACPPowerModel",
        "acr": "ACRPowerModel",
        "act": "ACTPowerModel",
        "ivr": "IVRPowerModel",
        "dcp": "DCPPowerModel",
        "dcmp": "DCMPPowerModel",
        "sdp": "SDPWRMPowerModel",
        "sparse_sdp": "SparseSDPWRMPowerModel",
    }
    canonical_name = aliases.get(normalized, formulation.strip())
    for name, formulation_type in FORMULATION_REGISTRY.items():
        if name.lower() == canonical_name.lower():
            return formulation_type()
    choices = ", ".join(FORMULATION_REGISTRY)
    raise ValueError(f"Unknown ACOPF formulation {formulation!r}; expected one of {choices}")


def implemented_formulations() -> tuple[str, ...]:
    """Return formulation names with a model builder implementation."""
    return tuple(
        formulation.name
        for formulation in (formulation_type() for formulation_type in _FORMULATION_TYPES)
        if formulation.implemented
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
