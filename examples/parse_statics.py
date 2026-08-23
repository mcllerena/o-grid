from o_grid.models import ACBus
from o_grid.statics import NtwFileParser
from o_grid.statics.ntw_models import DCLink, ShuntDevice

# parsed = NtwFileParser("tests/data/ntw/9bus.ntw")
parsed = NtwFileParser("tests/data/ntw/CASO01.NTW")
system = parsed.parse()

acbuses = [bus for bus in system.get_components(ACBus)]
dclinks = [link for link in system.get_components(DCLink)]
shunts = [shunt for shunt in system.get_components(ShuntDevice)]