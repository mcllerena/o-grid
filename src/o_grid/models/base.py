"""Base classes for o_grid models."""

from __future__ import annotations

from typing import Annotated, ClassVar
from uuid import UUID, uuid4

from infrasys import Component
from pydantic import Field


class OGridComponent(Component):
    """Base component with common metadata fields for o_grid models."""

    uuid: Annotated[
        UUID,
        Field(description="Unique identifier for the component."),
    ] = Field(default_factory=uuid4)
    available: Annotated[
        bool,
        Field(description="Whether the component is available for operation."),
    ] = True
    category: Annotated[
        str | None,
        Field(description="Category that this component belongs to."),
    ] = None
    ext: dict = Field(default_factory=dict, description="Additional metadata for the component.")


class AnaredeComponent(OGridComponent):
    """Base infrasys component for ANAREDE-derived models."""

    name: str = ""
    block: ClassVar[str] = ""
