"""Parser for ANAREDE dynamic-model (``.dyn``) files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

NumericValue = float | str


@dataclass(frozen=True, slots=True)
class DynDataRecord:
    """One slash-terminated data record belonging to a dynamic model."""

    line_number: int
    values: tuple[NumericValue, ...]
    raw: str


@dataclass(frozen=True, slots=True)
class DynModel:
    """A dynamic model header and its data records."""

    model: str
    name: str
    headers: tuple[tuple[str, ...], ...]
    records: tuple[DynDataRecord, ...]
    start_line: int


@dataclass(frozen=True, slots=True)
class DynFile:
    """Parsed contents of a ``.dyn`` file."""

    source: Path
    version: str
    models: tuple[DynModel, ...]


class DynFileParser:
    """Parse ANAREDE ``.dyn`` files into structured, lossless records.

    The format is model-oriented rather than a single rectangular table. A
    model starts with an ``SMxx`` line, comment lines beginning with ``!``
    describe the following record, and records end at ``/``. Values are
    converted to ``float`` when possible; identifiers and sentinel values are
    retained as strings.
    """

    _model_pattern = re.compile(r"^\s*(SM\d+)\s+(.*?)\s*$", re.IGNORECASE)

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.file = self.parse()
        self.version = self.file.version
        self.models = self.file.models

    def parse(self, path: str | Path | None = None) -> DynFile:
        """Parse *path*, or the path supplied to the constructor."""
        source = Path(path) if path is not None else self.path
        text = source.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        version = self._parse_version(lines)
        models: list[DynModel] = []
        current: dict[str, object] | None = None
        pending_headers: list[tuple[str, ...]] = []

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped == "!":
                continue
            if line_number == 1 and re.match(r"^VERSION\b", stripped, re.IGNORECASE):
                continue

            match = self._model_pattern.match(line)
            if match:
                if current is not None:
                    models.append(self._build_model(current))
                current = {
                    "model": match.group(1).upper(),
                    "name": match.group(2).strip(),
                    "headers": [],
                    "records": [],
                    "start_line": line_number,
                }
                pending_headers = []
                continue

            if stripped.startswith("!"):
                if current is not None:
                    header = tuple(stripped[1:].split())
                    if header:
                        pending_headers.append(header)
                continue

            if current is None:
                raise ValueError(f"Unexpected data before a model at line {line_number}")
            record_text = line[: line.rfind("/")].strip() if "/" in line else stripped
            values = tuple(self._parse_value(token) for token in record_text.split())
            headers = cast(list[tuple[str, ...]], current["headers"])
            records = cast(list[DynDataRecord], current["records"])
            headers.extend(pending_headers)
            pending_headers = []
            records.append(DynDataRecord(line_number, values, line.rstrip()))

        if current is not None:
            models.append(self._build_model(current))
        if not models:
            raise ValueError(f"No dynamic models found in {source}")
        return DynFile(source=source, version=version, models=tuple(models))

    @staticmethod
    def _parse_version(lines: list[str]) -> str:
        for line in lines:
            if line.strip():
                match = re.fullmatch(r"VERSION\s+(.+?)\s*", line.strip(), re.IGNORECASE)
                if match:
                    return match.group(1)
                break
        raise ValueError("Dynamic file does not start with a VERSION declaration")

    @staticmethod
    def _parse_value(token: str) -> NumericValue:
        try:
            return float(token)
        except ValueError:
            return token

    @staticmethod
    def _build_model(values: dict[str, object]) -> DynModel:
        headers = values["headers"]
        records = values["records"]
        start_line = values["start_line"]
        headers = cast(list[tuple[str, ...]], headers)
        records = cast(list[DynDataRecord], records)
        assert isinstance(start_line, int)
        return DynModel(
            model=str(values["model"]),
            name=str(values["name"]),
            headers=tuple(headers),
            records=tuple(records),
            start_line=start_line,
        )