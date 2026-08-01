from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser

data_path = Path("tests/data/pwf/LEN_A_4_2020_SECO_2023VM_SE_EXP_N.pwf")

# Parse
parse_cfg = AnaredeConfig(
    system_name="CASO_FINAL_EQV2020",
    pwf_path=str(data_path),
)
parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=data_path.parent))
parsed_system = AnaredeParser.from_context(parse_ctx).run().system
