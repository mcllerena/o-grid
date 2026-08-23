"""Parser for ANAREDE dynamic-contingency (``.evt``) files."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DynamicEvent:
    """One event in a dynamic contingency."""

    event_type: int
    bus_1: int | str
    bus_2: int | str
    circuit_id: str
    parameter_1: float
    parameter_2: float
    parameter_3: float
    bus_1_name: str
    bus_2_name: str
    parameter_4: float
    line_number: int
    raw: str

    @property
    def event_time(self) -> float:
        """Return the event time stored in parameter 3."""
        return self.parameter_3


@dataclass(frozen=True, slots=True)
class DynamicContingency:
    """A numbered contingency and its ordered events."""

    number: int
    identifier: str
    events: tuple[DynamicEvent, ...]
    line_number: int
    raw: str


@dataclass(frozen=True, slots=True)
class EvtFile:
    """Parsed contents of an ANAREDE ``.evt`` file."""

    source: Path
    total_simulation_time: float
    contingencies: tuple[DynamicContingency, ...]


class EvtFileParser:
    """Parse ANAREDE dynamic-contingency files into structured records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.file = self.parse()
        self.total_simulation_time = self.file.total_simulation_time
        self.contingencies = self.file.contingencies

    def parse(self, path: str | Path | None = None) -> EvtFile:
        """Parse *path*, or the path supplied to the constructor."""
        source = Path(path) if path is not None else self.path
        lines = source.read_text(encoding="utf-8-sig").splitlines()
        first_line = next(
            ((line_number, line) for line_number, line in enumerate(lines, 1) if line.strip()),
            None,
        )
        if first_line is None:
            raise ValueError(f"Event file is empty: {source}")
        total_line_number, total_line = first_line
        total_simulation_time = _parse_float(
            _tokens(total_line, total_line_number)[0], total_line_number, "total simulation time"
        )

        contingencies: list[DynamicContingency] = []
        current_number: int | None = None
        current_identifier = ""
        current_line_number = 0
        current_raw = ""
        current_events: list[DynamicEvent] = []
        in_contingency = False

        for line_number, line in enumerate(lines[total_line_number:], total_line_number + 1):
            if not line.strip():
                continue
            tokens = _tokens(line, line_number)
            marker = _integer_or_none(tokens[0])
            if marker == -999:
                break
            if marker == -99:
                if in_contingency:
                    assert current_number is not None
                    contingencies.append(
                        DynamicContingency(
                            number=current_number,
                            identifier=current_identifier,
                            events=tuple(current_events),
                            line_number=current_line_number,
                            raw=current_raw,
                        )
                    )
                    current_number = None
                    current_events = []
                    in_contingency = False
                continue
            if len(tokens) == 2 and marker is not None:
                if in_contingency:
                    raise ValueError(
                        f"Contingency header before -99 terminator at line {line_number}"
                    )
                current_number = marker
                current_identifier = tokens[1]
                current_line_number = line_number
                current_raw = line.rstrip()
                current_events = []
                in_contingency = True
                continue
            if not in_contingency:
                raise ValueError(f"Event found outside a contingency at line {line_number}")
            current_events.append(_parse_event(tokens, line_number, line))

        if in_contingency:
            assert current_number is not None
            contingencies.append(
                DynamicContingency(
                    number=current_number,
                    identifier=current_identifier,
                    events=tuple(current_events),
                    line_number=current_line_number,
                    raw=current_raw,
                )
            )
        return EvtFile(
            source=source,
            total_simulation_time=total_simulation_time,
            contingencies=tuple(contingencies),
        )


def _parse_event(tokens: list[str], line_number: int, raw: str) -> DynamicEvent:
    if len(tokens) != 10:
        raise ValueError(f"Expected 10 event fields at line {line_number}, found {len(tokens)}")
    return DynamicEvent(
        event_type=_parse_int(tokens[0], line_number, "event type"),
        bus_1=_parse_bus_reference(tokens[1], line_number),
        bus_2=_parse_bus_reference(tokens[2], line_number),
        circuit_id=tokens[3],
        parameter_1=_parse_float(tokens[4], line_number, "parameter 1"),
        parameter_2=_parse_float(tokens[5], line_number, "parameter 2"),
        parameter_3=_parse_float(tokens[6], line_number, "parameter 3"),
        bus_1_name=tokens[7],
        bus_2_name=tokens[8],
        parameter_4=_parse_float(tokens[9], line_number, "parameter 4"),
        line_number=line_number,
        raw=raw.rstrip(),
    )


def _tokens(line: str, line_number: int) -> list[str]:
    try:
        return shlex.split(line[: line.rfind("/")] if "/" in line else line)
    except ValueError as exc:
        raise ValueError(f"Invalid quoting at line {line_number}") from exc


def _parse_bus_reference(value: str, line_number: int) -> int | str:
    integer = _integer_or_none(value)
    if integer is not None:
        return integer
    if value:
        return value
    raise ValueError(f"Invalid bus reference at line {line_number}")


def _parse_int(value: str, line_number: int, field: str) -> int:
    integer = _integer_or_none(value)
    if integer is None:
        raise ValueError(f"Invalid {field} at line {line_number}: {value!r}")
    return integer


def _parse_float(value: str, line_number: int, field: str) -> float:
    try:
        return float(value.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise ValueError(f"Invalid {field} at line {line_number}: {value!r}") from exc


def _integer_or_none(value: str) -> int | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else None
