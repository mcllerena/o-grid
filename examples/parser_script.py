from pathlib import Path

from r2x_core import DataStore, PluginContext

from o_grid import AnaredeConfig, AnaredeParser
from o_grid.models import ACBus

data_path = Path("tests/data/pwf/br-data-2026-1q")

br_data_2026_1q_list = []

for file in data_path.iterdir():
    if file.suffix == ".PWF":
        print(f"Found PWF file: {file.name}")
        parse_cfg = AnaredeConfig(
            system_name=file.stem,
            pwf_path=str(file),
        )
        parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=data_path.parent))
        parsed_system = AnaredeParser.from_context(parse_ctx).run().system

        br_data_2026_1q_list.append(parsed_system)


total_load_by_sys = []
for system in br_data_2026_1q_list:
    total_load = sum(bus.active_load.magnitude for bus in system.get_components(ACBus))
    total_load_by_sys.append((system.name, system.description, total_load))


# Parse
# parse_cfg = AnaredeConfig(
#     system_name="CASO_FINAL_EQV2020",
#     pwf_path=str(data_path),
# )
# parse_ctx = PluginContext(config=parse_cfg, store=DataStore(path=data_path.parent))
# parsed_system = AnaredeParser.from_context(parse_ctx).run().system
