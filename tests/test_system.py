"""Tests for the ANAREDE-aware infrasys ``System`` summary."""

from __future__ import annotations

from infrasys.system import SystemInfo

from o_grid.models import IndividualizedLoad, PowerFlowOption, ProgramConstant
from o_grid.system import AnaredeSystem, AnaredeSystemInfo


def _demo_system() -> AnaredeSystem:
    system = AnaredeSystem(name="demo")
    system.add_component(IndividualizedLoad(name="87_9", bus=87))
    system.add_component(PowerFlowOption(name="QLIM", option="QLIM"))
    system.add_component(ProgramConstant(name="BASE", mnemonic="BASE"))
    return system


def test_extract_system_counts_excludes_power_flow_types() -> None:
    info = AnaredeSystemInfo(system=_demo_system())

    _, _, type_count, _ = info.extract_system_counts()
    assert "IndividualizedLoad" in type_count
    assert "PowerFlowOption" not in type_count
    assert "ProgramConstant" not in type_count

    # The base counts still report every component type.
    _, _, full_count, _ = SystemInfo.extract_system_counts(info)
    assert full_count["PowerFlowOption"] == 1
    assert full_count["ProgramConstant"] == 1


def test_info_renders_power_flow_information_table(capsys) -> None:
    _demo_system().info()

    out = capsys.readouterr().out
    assert "Component Information" in out
    assert "Power Flow Information" in out
    assert "PowerFlowOption" in out
    assert "ProgramConstant" in out
