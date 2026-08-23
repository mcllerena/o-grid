from pathlib import Path

import pytest

from o_grid.dynamics import DynFileParser


def test_dyn_file_parser_reads_9bus_file() -> None:
    parsed = DynFileParser(Path(__file__).parent / "data" / "dyn" / "9bus.dyn")

    assert parsed.version == "1"
    assert [model.model for model in parsed.models] == ["SM04", "SM05", "SM05"]
    assert [model.records[0].values[0] for model in parsed.models] == [1.0, 2.0, 3.0]
    assert parsed.models[0].records[0].values[2] == "AVR03"
    assert parsed.models[2].records[-2].values == (1.0, 0.0, 0.08, 1.0, 1.0, 1.2, "_0")


def test_dyn_file_parser_requires_version(tmp_path: Path) -> None:
    path = tmp_path / "invalid.dyn"
    path.write_text("SM04 TEST\n 1 /\n", encoding="utf-8")

    with pytest.raises(ValueError, match="VERSION"):
        DynFileParser(path)
