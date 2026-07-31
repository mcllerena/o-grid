"""Configuration models for o_grid parser and exporter plugins."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from r2x_core.plugin_config import PluginConfig


class AnaredeConfig(PluginConfig):
	"""Configuration for ANAREDE parser plugin."""

	model_year: Annotated[
		int | list[int] | None,
		Field(description="Model solve year(s)"),
	] = None
	system_name: Annotated[
		str | None,
		Field(default=None, description="Power system name"),
	] = None
	pwf_path: Annotated[
		str | None,
		Field(default=None, description="Path to ANAREDE .pwf case file"),
	] = None
	mapping_path: Annotated[
		str | None,
		Field(default=None, description="Optional override path for mapping JSON"),
	] = None
	scenario: Annotated[
		str,
		Field(default="base", description="Scenario identifier"),
	] = "base"
	models: Annotated[
		tuple[str, ...],
		Field(
			default=("o_grid.models",),
			description="Module path(s) for o_grid component classes",
		),
	] = ("o_grid.models",)
