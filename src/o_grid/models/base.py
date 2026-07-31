"""Base classes for o_grid models."""

from __future__ import annotations

from typing import Annotated, ClassVar
from uuid import UUID, uuid4

from infrasys import Component
from pydantic import Field, computed_field


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def class_type(self) -> str:
        """Return the concrete class name for serialization and debugging."""
        return type(self).__name__


class AnaredeComponent(OGridComponent):
    """Base infrasys component for ANAREDE-derived models."""

    name: str = ""
    record_index: int = 0
    block: ClassVar[str] = ""
