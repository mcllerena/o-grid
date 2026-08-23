from pathlib import Path

import pytest

from o_grid.dynamics import EvtFileParser

EVT_PATH = Path(__file__).parent / "data" / "evt" / "9bus.evt"


def test_evt_file_parser_reads_9bus_file() -> None:
    parsed = EvtFileParser(EVT_PATH)

    assert parsed.total_simulation_time == 32.0
    assert len(parsed.contingencies) == 10
    assert parsed.contingencies[0].identifier.strip() == "Steady state"
    assert len(parsed.contingencies[1].events) == 3
    event = parsed.contingencies[1].events[0]
    assert (event.event_type, event.bus_1, event.bus_2) == (3, 4, 0)
    assert event.parameter_3 == 0.3
    assert event.bus_1_name.strip() == "Bus 4"


def test_evt_file_parser_rejects_malformed_event(tmp_path: Path) -> None:
    path = tmp_path / "invalid.evt"
    path.write_text("1.0 /\n1 'case' /\n3 1 0 0 0.0 /\n-99 /\n-999 /\n")

    with pytest.raises(ValueError, match="10 event fields"):
        EvtFileParser(path)
