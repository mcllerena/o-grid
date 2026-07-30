"""Case and metadata models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models.base import AnaredeComponent, ParsedScalar


class CaseTitle(AnaredeComponent):
    """Case title/description entry."""

    title_line: Annotated[
        ParsedScalar,
        Field(
            description="System title/description line",
        ),
    ] = None
