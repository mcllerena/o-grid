"""r2x-core plugin wrappers for ANAREDE and MATPOWER parsing."""

from __future__ import annotations

from pathlib import Path

from infrasys import System
from r2x_core import Plugin
from rust_ok import Err, Ok, Result

from o_grid.matpower import parse_matpower_system
from o_grid.parser import parse_anarede_system
from o_grid.plugin_config import AnaredeConfig, MatpowerConfig


class AnaredeParser(Plugin[AnaredeConfig]):
    """Plugin that parses ANAREDE `.pwf` data into an infrasys System."""

    def on_build(self) -> Result[System, str]:
        config = self._require_config()
        if not config.pwf_path:
            return Err("pwf_path must be specified in AnaredeConfig")

        if config.mapping_path:
            parsed = parse_anarede_system(
                Path(config.pwf_path),
                mapping_path=Path(config.mapping_path),
                system_name=config.system_name or "ANAREDE",
            )
        else:
            parsed = parse_anarede_system(
                Path(config.pwf_path),
                system_name=config.system_name or "ANAREDE",
            )
        self.ctx.metadata["parsed"] = parsed
        return Ok(parsed.system)

    def _require_config(self) -> AnaredeConfig:
        config = self.config
        if not isinstance(config, AnaredeConfig):
            raise ValueError("AnaredeParser requires an AnaredeConfig instance")
        return config


class MatPowerParser(Plugin[MatpowerConfig]):
    """Plugin that parses MATPOWER `.m` data into an infrasys System."""

    def on_build(self) -> Result[System, str]:
        config = self._require_config()
        if not config.pwf_path:
            return Err("pwf_path must be specified in MatpowerConfig")
        parsed = parse_matpower_system(
            Path(config.pwf_path),
            system_name=config.system_name or "MATPOWER",
            base_mva=config.base_mva,
        )
        self.ctx.metadata["parsed"] = parsed
        return Ok(parsed.system)

    def _require_config(self) -> MatpowerConfig:
        config = self.config
        if not isinstance(config, MatpowerConfig):
            raise ValueError("MatPowerParser requires a MatpowerConfig instance")
        return config
