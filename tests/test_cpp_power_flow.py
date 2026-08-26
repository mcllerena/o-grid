import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from o_grid.cpp import adapter, ntw2dat, pwf2dat
from o_grid.cpp.dat_writer import format_dat_value, write_dat

DATA = Path(__file__).parent / "data"


def test_format_dat_value_and_write_dat(tmp_path: Path) -> None:
    assert format_dat_value(None) == "0"
    assert format_dat_value("") == "0"
    assert format_dat_value(".") == "0"
    assert format_dat_value(True) == "1"
    assert format_dat_value(False) == "0"
    assert format_dat_value(1.25) == "1.25"
    assert format_dat_value(3) == "3"
    assert format_dat_value("bus 1") == '"bus 1"'

    destination = write_dat(
        tmp_path / "case.dat",
        "case.pwf",
        {"DBAR": [{"number": 1, "name": "Bus 1", "value": 1.25}], "EMPTY": []},
        {"field_order": {"DBAR": ["name", "number"]}, "name_aliases": {"name": "Name"}},
    )
    text = destination.read_text(encoding="utf-8")
    assert "# Generated from case.pwf" in text
    assert "param: DBAR:" in text
    assert '"Bus 1"' in text
    assert text.endswith("\n")


def test_pwf2dat_converts_fixture_and_supports_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = DATA / "pwf" / "d_9nodes.pwf"
    destination = pwf2dat.convert(source, tmp_path / "case.dat")
    assert destination.exists()
    assert "param: DBAR:" in destination.read_text(encoding="utf-8")

    assert pwf2dat.main([str(source), str(tmp_path / "cli.dat")]) == 0
    assert "Wrote" in capsys.readouterr().out


def test_pwf2dat_parse_handles_sections_and_banks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic.pwf"
    source.write_text(
        "\nDOPC\nQLIM L VLIM D\nDCTE\nBASE 100 TLVC .05\n"
        "DBSH\n 1  2\nDBSH_BANK\n 3  4\nFBAN\n"
        "DBAR\n(comment)\n99999 ignored\n\nUNKN1\nignored\n",
        encoding="cp1252",
    )
    mapping = {
        "DOPC": {},
        "DCTE": {},
        "DBSH": {"fields": {"bus": {"column": {"start": 1, "end": 2}}}},
        "DBSH_BANK": {"fields": {"stage": {"column": {"start": 1, "end": 2}}}},
        "DBAR": {"fields": {"bus": {"column": {"start": 1, "end": 2}}}},
    }
    sections = pwf2dat._parse(source, mapping)
    assert sections["DOPC"] == [{"option": "QLIM", "state": "L"}, {"option": "VLIM", "state": "D"}]
    assert sections["DCTE"] == [
        {"mnemonic": "BASE", "value": 100},
        {"mnemonic": "TLVC", "value": 0.05},
    ]
    assert sections["DBSH"][0]["bus"] == 1
    assert sections["DBSH_BANK"][0]["parent_record_index"] == 1
    assert "DBAR" not in sections

    monkeypatch.setattr(pwf2dat, "load_mapping", lambda _: mapping)
    assert pwf2dat.convert(source, tmp_path / "synthetic.dat").exists()


def test_ntw2dat_converts_fixture_and_helpers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = DATA / "ntw" / "9bus.ntw"
    destination = ntw2dat.convert(source, tmp_path / "case.dat")
    text = destination.read_text(encoding="utf-8")
    assert "param: DBAR:" in text
    assert "param: DLIN:" in text

    assert ntw2dat._bus_type("PQ") == 0
    assert ntw2dat._bus_type("PV") == 1
    assert ntw2dat._bus_type("REF") == 2
    assert ntw2dat._bus_type("SLACK") == 2
    assert ntw2dat._bus_type(7) == 7
    assert ntw2dat._magnitude(None, 2.0) == 2.0
    assert ntw2dat._magnitude("bad", 3.0) == 3.0

    assert ntw2dat.main([str(source), str(tmp_path / "cli.dat")]) == 0
    assert "Wrote" in capsys.readouterr().out


def _parsed_report(tmp_path: Path) -> SimpleNamespace:
    bus = SimpleNamespace(number=1, active_load=10.0, reactive_load=2.0)
    return SimpleNamespace(source=tmp_path / "case.dat", components_by_block={"DBAR": [bus]})


def test_adapter_parses_report_and_summary_helpers(tmp_path: Path) -> None:
    parsed = _parsed_report(tmp_path)
    report = """Base MVA: 100
Converged: yes
Iterations: 4
Max mismatch: 0.001
PYOMO_WARM_START_BEGIN
BUS 1 1.02 0.1 0 110 22 0
PYOMO_WARM_START_END
Branch flows and losses
1 1 2 10 2 -9 -1 0 50 1 1 0
"""
    result = adapter._parse_report(report, parsed, "newton-raphson")
    assert result.converged is True
    assert result.iterations == 4
    assert result.buses[0].active_injection_pu == pytest.approx(1.0)
    assert len(result.branches) == 1
    assert adapter._summary_value(report, "Missing") == ""
    assert adapter._summary_float(report, "Missing", 3.0) == 3.0
    assert adapter._magnitude("bad") == 0.0

    with pytest.raises(RuntimeError, match="PYOMO_WARM_START"):
        adapter._parse_buses("", parsed, 100.0)
    with pytest.raises(RuntimeError, match="solved bus"):
        adapter._parse_buses("PYOMO_WARM_START_BEGIN\nPYOMO_WARM_START_END", parsed, 100.0)


def test_adapter_solve_with_cpp_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    parsed = _parsed_report(tmp_path)
    report = """Base MVA: 100
Converged: no
Iterations: 2
Max mismatch: 0.5
PYOMO_WARM_START_BEGIN
BUS 1 1.0 0.0 0 10 2 0
PYOMO_WARM_START_END
"""
    executable = tmp_path / "solver.exe"
    monkeypatch.setattr(adapter, "_executable", lambda _: executable)

    def run(command, **kwargs):
        Path(command[command.index("--save") + 1]).write_text(report, encoding="utf-8")
        return SimpleNamespace(returncode=2, stdout="native out\n", stderr="native err\n")

    monkeypatch.setattr(adapter.subprocess, "run", run)
    result, output = adapter.solve_with_cpp(
        parsed,
        solver_name="newton-raphson",
        tolerance=1e-6,
        max_iterations=5,
        print_iterations=True,
    )
    assert result.converged is False
    assert output == "native out\nnative err\n"
    assert "native out" in capsys.readouterr().out

    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad"),
    )
    with pytest.raises(RuntimeError, match="exit code 1"):
        adapter.solve_with_cpp(
            parsed,
            solver_name="newton-raphson",
            tolerance=None,
            max_iterations=5,
            print_iterations=False,
        )

    monkeypatch.setattr(
        adapter,
        "_executable",
        lambda _: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    with pytest.raises(FileNotFoundError):
        adapter._executable("newton-raphson")


def test_adapter_dispatches_pwf_and_ntw_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = _parsed_report(tmp_path)
    report = "PYOMO_WARM_START_BEGIN\nBUS 1 1.0 0.0 0 10 2 0\nPYOMO_WARM_START_END"
    monkeypatch.setattr(adapter, "_executable", lambda _: tmp_path / "solver")
    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda command, **kwargs: (
            Path(command[command.index("--save") + 1]).write_text(report, encoding="utf-8"),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        )[1],
    )
    for suffix, converter in ((".pwf", "convert_pwf"), (".ntw", "convert_ntw")):
        source = tmp_path / f"case{suffix}"
        source.write_text("input", encoding="utf-8")
        parsed.source = source
        called = []
        monkeypatch.setattr(adapter, converter, lambda *args: called.append(args))
        adapter.solve_with_cpp(
            parsed,
            solver_name="newton-raphson",
            tolerance=None,
            max_iterations=2,
            print_iterations=False,
        )
        assert called


def test_adapter_parse_report_requires_bus_results(tmp_path: Path) -> None:
    parsed = _parsed_report(tmp_path)
    report = "Base MVA: bad\nConverged: yes\nPYOMO_WARM_START_BEGIN\nPYOMO_WARM_START_END"
    with pytest.raises(RuntimeError, match="solved bus"):
        adapter._parse_report(report, parsed, "newton-raphson")


def test_adapter_rejects_unsupported_input(tmp_path: Path) -> None:
    parsed = _parsed_report(tmp_path)
    parsed.source = tmp_path / "case.csv"
    with pytest.raises(ValueError, match="supports .pwf"):
        adapter.solve_with_cpp(
            parsed,
            solver_name="newton-raphson",
            tolerance=None,
            max_iterations=2,
            print_iterations=False,
        )


def test_converter_module_entry_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pwf = DATA / "pwf" / "d_9nodes.pwf"
    ntw = DATA / "ntw" / "9bus.ntw"
    monkeypatch.setattr(sys, "argv", ["pwf2dat", str(pwf), str(tmp_path / "module-pwf.dat")])
    with pytest.raises(SystemExit) as pwf_exit:
        runpy.run_module("o_grid.cpp.pwf2dat", run_name="__main__")
    assert pwf_exit.value.code == 0
    monkeypatch.setattr(sys, "argv", ["ntw2dat", str(ntw), str(tmp_path / "module-ntw.dat")])
    with pytest.raises(SystemExit) as ntw_exit:
        runpy.run_module("o_grid.cpp.ntw2dat", run_name="__main__")
    assert ntw_exit.value.code == 0
