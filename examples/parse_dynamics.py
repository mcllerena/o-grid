from o_grid.dynamics import DynFileParser

parsed = DynFileParser("tests/data/dyn/9bus.dyn")

print(parsed.version)
print(parsed.models)
