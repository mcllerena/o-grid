"""MATPOWER case-level constants mapped to o-grid control records."""

from __future__ import annotations

from o_grid.models.control import ProgramConstant
from o_grid.units import ApparentPower


def ProgramConstants(base_mva: float) -> list[ProgramConstant]:
    """Build the case ``DCTE`` records from the MATPOWER base MVA."""
    return [
        ProgramConstant(
            name="program_constant_BASE",
            mnemonic="BASE",
            value=ApparentPower(base_mva, "MVA"),
        )
    ]
