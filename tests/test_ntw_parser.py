from pathlib import Path

from o_grid.models import ACBus, ACLine, Area, Generator, IndividualizedLoad
from o_grid.statics.ntw_models import (
    ACBus as NtwACBus,
)
from o_grid.statics.ntw_models import (
    Generator as NtwGenerator,
)
from o_grid.statics.ntw_models import (
    Load,
    Substation,
    Transformer,
    TransmissionLine,
    Zone,
)
from o_grid.statics.ntw_parser import NtwFileParser


def test_ntw_parser_builds_infrasys_system() -> None:
    system = NtwFileParser(Path(__file__).parent / "data" / "ntw" / "9bus.ntw").system

    buses = list(system.get_components(ACBus))
    assert len(buses) == 9
    assert buses[0].number == 1
    assert buses[1].area is not None
    assert buses[1].area.area_number == 2
    assert len(list(system.get_components(NtwACBus))) == 9
    assert list(system.get_components(NtwACBus))[1].bus_id == 2
    assert len(list(system.get_components(Load))) == 3
    assert len(list(system.get_components(NtwGenerator))) == 3
    assert len(list(system.get_components(TransmissionLine))) == 6
    assert len(list(system.get_components(Transformer))) == 3
    assert len(list(system.get_components(Area))) == 3
    assert len(list(system.get_components(Zone))) == 1
    assert len(list(system.get_components(Substation))) == 6
    assert len(list(system.get_components(IndividualizedLoad))) == 3
    assert len(list(system.get_components(Generator))) == 3
    assert len(list(system.get_components(ACLine))) == 6
