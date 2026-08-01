from __future__ import annotations

from pathlib import Path

import pytest
from infrasys import System
from r2x_core.plugin_config import PluginConfig
from r2x_core.plugin_context import PluginContext

from o_grid.parser import MAPPING_PATH
from o_grid.plugin_config import AnaredeConfig
from o_grid.plugin_parser import AnaredeParser


def _build_plugin(config: PluginConfig) -> AnaredeParser:
    plugin = AnaredeParser()
    plugin._ctx = PluginContext(config=config)
    return plugin


def test_on_build_parses_pwf(data_folder: Path) -> None:
    pwf = data_folder / "anarede" / "d_33nodes.pwf"
    plugin = _build_plugin(AnaredeConfig(pwf_path=str(pwf), system_name="plugin-demo"))

    result = plugin.on_build()

    assert result.is_ok()
    system = result.unwrap()
    assert isinstance(system, System)
    assert system.name == "plugin-demo"
    assert plugin.ctx.metadata["parsed"].system is system


def test_on_build_with_mapping_path(data_folder: Path) -> None:
    pwf = data_folder / "anarede" / "d_33nodes.pwf"
    plugin = _build_plugin(AnaredeConfig(pwf_path=str(pwf), mapping_path=str(MAPPING_PATH)))

    result = plugin.on_build()

    assert result.is_ok()
    assert result.unwrap().name == "ANAREDE"


def test_on_build_without_pwf_path_returns_err() -> None:
    plugin = _build_plugin(AnaredeConfig())

    result = plugin.on_build()

    assert result.is_err()
    assert "pwf_path" in result.unwrap_err()


def test_require_config_rejects_foreign_config() -> None:
    class OtherConfig(PluginConfig):
        pass

    plugin = _build_plugin(OtherConfig())

    with pytest.raises(ValueError, match="requires an AnaredeConfig"):
        plugin._require_config()
