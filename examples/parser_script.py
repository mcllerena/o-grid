from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser

data_path = Path("tests/data/anarede/d_33nodes_dcer_dcsc.pwf")

# Parse
parse_cfg = AnaredeConfig(
    system_name="ANAREDE-9",
    pwf_path=str(data_path),
)
parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=data_path.parent))
parsed_system = AnaredeParser.from_context(parse_ctx).run().system
