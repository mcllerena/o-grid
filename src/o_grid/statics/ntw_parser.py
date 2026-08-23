"""Parser for ANAREDE static network (``.ntw``) files."""

from __future__ import annotations

import csv
import re
import shlex
from pathlib import Path
from typing import Any

from infrasys import Component
from loguru import logger

from o_grid.models.named_tuples import MinMax
from o_grid.statics.ntw_models import (
    ACBus,
    Area,
    BreakerConfiguration,
    DCLink,
    FACTSDevice,
    Generator,
    ImpedanceCorrection,
    InductionMotor,
    LineMutualImpedance,
    Load,
    Owner,
    SeriesCapacitor,
    ShuntDevice,
    Substation,
    Transformer,
    TransmissionLine,
    Zone,
)
from o_grid.system import AnaredeSystem
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Distance,
    Percentage,
    PerUnit,
    ReactivePower,
    Resistance,
    Voltage,
)


class NtwFileParser:
    """Parse an ANAREDE ``.ntw`` file into an :class:`AnaredeSystem`.

    NTW records are comma-separated and grouped by section. The parser keeps
    every source row in the component ``ext`` metadata while mapping the
    network sections used by the typed o-grid models.
    """

    _section_pattern = re.compile(r"BEGIN (.+?) DATA", re.IGNORECASE)

    def __init__(self, path: str | Path, system_name: str | None = None) -> None:
        self.path = Path(path)
        self.version = self._read_version()
        self.component_version = 6 if self.version > 7 else self.version
        self.system = self.parse(system_name=system_name)

    def parse(self, system_name: str | None = None) -> AnaredeSystem:
        """Parse the configured file and return its populated infrasys system."""
        lines = self.path.read_bytes().decode("cp1252", errors="replace").splitlines()
        system = AnaredeSystem(name=system_name or self.path.stem)
        sections: dict[str, list[tuple[int, list[str], str]]] = {}
        section: str | None = None
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            match = self._section_pattern.search(stripped)
            if match:
                section = self._normalize_section(match.group(1))
                sections.setdefault(section, [])
                continue
            if not stripped:
                continue
            if stripped.startswith("!"):
                continue
            if section is None and not stripped.startswith("("):
                continue
            values = self._tokens(line)
            if values and values[0].startswith("("):
                if section is None:
                    section = "BUS"
                    sections.setdefault(section, [])
                continue
            if values and values[0] == "0" and len(values) <= 2:
                continue
            if section is not None:
                sections[section].append((line_number, values, line.rstrip()))

        components_by_block: dict[str, list[Component]] = {}
        areas = self._build_areas(sections.get("AREA", []))
        buses = self._build_buses(sections.get("BUS", []), areas)
        components_by_block["DBAR"] = list(buses)
        self._log_block_progress("DBAR", components_by_block)
        self._add_areas(system, components_by_block, buses, areas)
        self._add_components(
            system, components_by_block, "DZONE", self._build_zones(sections.get("ZONE", []))
        )
        self._add_components(
            system,
            components_by_block,
            "DSUBSTATION",
            self._build_substations(sections.get("SUBSTATION", [])),
        )
        self._add_all(system, buses)
        self._add_components(
            system, components_by_block, "DCAI", self._build_loads(sections.get("LOAD", []))
        )
        self._add_components(
            system,
            components_by_block,
            "DGER",
            self._build_generators(sections.get("GENERATOR", [])),
        )
        self._add_components(
            system,
            components_by_block,
            "DLIN",
            self._build_lines(sections.get("TRANSMISSION LINE", [])),
        )
        self._add_components(
            system,
            components_by_block,
            "DLIN_TRANSFORMER",
            self._build_transformers(sections.get("TRANSFORMER", [])),
        )
        section_builders = (
            ("DSHUNT", "SHUNT", self._build_shunts),
            ("DSERIES_CAPACITOR", "SERIES CAPACITOR", self._build_series_capacitors),
            ("DDCLINK", "DCLINK", self._build_dc_links),
            ("DIMPEDANCE_CORRECTION", "IMPEDANCE CORRECTION", self._build_impedance_corrections),
            ("DLINE_MUTUAL_IMPEDANCE", "LINE MUTUAL IMPEDANCE", self._build_line_mutual_impedances),
            ("DINDUCTION_MOTOR", "INDUCTION MOTOR", self._build_induction_motors),
            ("DBREAKER_CONFIGURATION", "BREAKER CONFIGURATION", self._build_breaker_configurations),
            ("DFACTS", "FACTS", self._build_facts),
            ("DOWNER", "OWNER", self._build_owners),
        )
        for block, section_name, builder in section_builders:
            components = builder(sections.get(section_name, []))
            self._add_components(system, components_by_block, block, components)
        total = sum(1 for _ in system._component_mgr.iter_all())
        logger.success("Successfully parsed {} component(s).", total)
        system.attach_parse_context(self.path, components_by_block, {})
        return system

    @staticmethod
    def _log_block_progress(block: str, components_by_block: dict[str, list[Component]]) -> None:
        count = len(components_by_block.get(block, []))
        if count:
            logger.info("Parsed {} section: {} record(s)", block, count)

    @staticmethod
    def _normalize_section(value: str) -> str:
        normalized = re.sub(r"\s+", " ", value.strip().upper()).removeprefix("OF ")
        aliases = {
            "SWITCHED SHUNT": "SHUNT",
            "TRANSFORMER IMPEDANCE CORRECTION": "IMPEDANCE CORRECTION",
        }
        return aliases.get(normalized, normalized)

    def _read_version(self) -> float:
        first_line = self.path.read_bytes().decode("cp1252", errors="replace").splitlines()[0]
        match = re.search(r"(\d+)\s+(\d+)", first_line)
        return float(f"{match.group(1)}.{match.group(2)}") if match else 6.0

    @staticmethod
    def _tokens(line: str) -> list[str]:
        if "," in line:
            tokens = next(csv.reader([line], skipinitialspace=True))
        else:
            tokens = shlex.split(line, comments=False, posix=True)
        return [token.strip().rstrip("/").strip().strip("'").strip() for token in tokens]

    @staticmethod
    def _looks_like_data(values: list[str]) -> bool:
        return bool(values) and bool(re.fullmatch(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?", values[0]))

    def _build_buses(
        self, rows: list[tuple[int, list[str], str]], areas: dict[int, Area]
    ) -> list[ACBus]:
        buses: list[ACBus] = []
        for line_number, values, raw in rows:
            if len(values) < 15:
                continue
            area_number = int(self._number(values[7]))
            bus = ACBus(
                name=values[1] or f"Bus_{values[0]}",
                bus_id=self._number(values[0]),
                bus_name=values[1],
                number=self._number(values[0]),
                bustype=self._number(values[3]),
                base_voltage=Voltage(self._float(values[2]), "kV"),
                initial_voltage=self._float(values[9]),
                voltage_magnitude=self._per_unit(values[9]),
                angle=Angle(self._float(values[10]), "degree"),
                voltage_angle=Angle(self._float(values[10]), "degree"),
                voltage_limits=MinMax(
                    min=self._float(values[12]),
                    max=self._float(values[11]),
                ),
                area=areas.get(
                    area_number, Area(name=f"Area_{area_number}", area_number=area_number)
                ),
                shunt_status=self._number(values[4]),
                shunt_conductance=ActivePower(self._float(values[5]), "MW"),
                shunt_susceptance=ReactivePower(self._float(values[6]), "MVAr"),
                zone_number=self._number(values[8]),
                overvoltage_threshold=self._per_unit(values[11]),
                undervoltage_threshold=self._per_unit(values[12]),
                emergency_overvoltage_threshold=self._per_unit(values[13]),
                emergency_undervoltage_threshold=self._per_unit(values[14]),
                owner_number=self._number(values[15]),
                substation_number=self._number(values[16]),
                bus_scheme=self._number(values[17]),
            )
            self._metadata(bus, line_number, raw, values)
            buses.append(bus)
        return buses

    def _build_areas(self, rows: list[tuple[int, list[str], str]]) -> dict[int, Area]:
        areas: dict[int, Area] = {}
        for line_number, values, raw in rows:
            if len(values) < 4:
                continue
            area_number = self._number(values[0])
            area_name = values[3] or f"Area_{area_number}"
            area = Area(name=area_name, area_number=area_number)
            area.area_name = area_name
            area.area_switch_id = int(self._number(values[1]))
            area.interchange_active_power = ActivePower(self._float(values[2]), "MW")
            self._metadata(area, line_number, raw, values)
            areas[int(area_number)] = area
        return areas

    def _build_zones(self, rows: list[tuple[int, list[str], str]]) -> list[Zone]:
        result: list[Zone] = []
        for line_number, values, raw in rows:
            if len(values) < 2:
                continue
            zone = Zone(
                name=values[1] or f"Zone_{values[0]}",
                zone_number=self._number(values[0]),
                zone_name=values[1],
            )
            self._metadata(zone, line_number, raw, values)
            result.append(zone)
        return result

    def _build_substations(self, rows: list[tuple[int, list[str], str]]) -> list[Substation]:
        result: list[Substation] = []
        for line_number, values, raw in rows:
            if len(values) < 4:
                continue
            substation = Substation(
                name=values[1] or f"Substation_{values[0]}",
                substation_number=self._number(values[0]),
                substation_name=values[1],
                latitude=self._float(values[2]),
                longitude=self._float(values[3]),
            )
            self._metadata(substation, line_number, raw, values)
            result.append(substation)
        return result

    def _build_loads(self, rows: list[tuple[int, list[str], str]]) -> list[Load]:
        result: list[Load] = []
        for line_number, values, raw in rows:
            if len(values) < 5:
                continue
            load = Load(
                name=f"Load_{values[0]}_{values[1]}",
                bus_id=self._number(values[0]),
                load_identifier=values[1],
                bus=self._number(values[0]),
                status=self._number(values[2]),
                active_power=ActivePower(self._float(values[3]), "MW"),
                reactive_power=ReactivePower(self._float(values[4]), "MVAr"),
                constant_power_active=ActivePower(self._float(values[3]), "MW"),
                constant_power_reactive=ReactivePower(self._float(values[4]), "MVAr"),
                constant_current_active=ActivePower(self._float(values[5]), "MW"),
                constant_current_reactive=ReactivePower(self._float(values[6]), "MVAr"),
                constant_impedance_active=ActivePower(self._float(values[7]), "MW"),
                constant_impedance_reactive=ReactivePower(self._float(values[8]), "MVAr"),
                owner_number=self._number(values[9]),
                zero_sequence_resistance=self._per_unit(values[10]),
                zero_sequence_reactance=self._per_unit(values[11]),
                load_name=values[12] if len(values) > 12 else "",
            )
            self._metadata(load, line_number, raw, values)
            result.append(load)
        return result

    def _build_generators(self, rows: list[tuple[int, list[str], str]]) -> list[Generator]:
        result: list[Generator] = []
        for line_number, values, raw in rows:
            if len(values) < 16:
                continue
            generator = Generator(
                name=f"Generator_{values[0]}_{values[1]}",
                bus_id=self._number(values[0]),
                generator_identifier=values[1],
                number=self._number(values[0]),
                active_generation=ActivePower(self._float(values[2]), "MW"),
                reactive_generation=ReactivePower(self._float(values[3]), "MVAr"),
                maximum_reactive_generation=ReactivePower(self._float(values[4]), "MVAr"),
                minimum_reactive_generation=ReactivePower(self._float(values[5]), "MVAr"),
                specified_voltage=self._per_unit(values[6]),
                controlled_bus_id=self._number(values[7]),
                power_base=ApparentPower(self._float(values[8]), "MVA"),
                transformer_resistance=self._per_unit(values[9]),
                transformer_reactance=self._per_unit(values[10]),
                transformer_tap=self._per_unit(values[11]),
                status=self._number(values[12]),
                remote_control_participation=self._percentage(values[13]),
                nominal_apparent_power=ApparentPower(self._float(values[8]), "MVA"),
                max_active_generation=ActivePower(self._float(values[14]), "MW"),
                min_active_generation=ActivePower(self._float(values[15]), "MW"),
                maximum_active_generation=ActivePower(self._float(values[14]), "MW"),
                minimum_active_generation=ActivePower(self._float(values[15]), "MW"),
                group_number=self._number(values[16]),
                unavailable=self._number(values[17]),
                owner_number=self._number(values[18]),
                ground_connection=self._number(values[19]),
                positive_sequence_resistance=self._per_unit(values[20]),
                positive_sequence_reactance=self._per_unit(values[21]),
                negative_sequence_resistance=self._per_unit(values[22]),
                negative_sequence_reactance=self._per_unit(values[23]),
                zero_sequence_resistance=self._per_unit(values[24]),
                zero_sequence_reactance=self._per_unit(values[25]),
                grounding_resistance=self._per_unit(values[26]),
                grounding_reactance=self._per_unit(values[27]),
                quadrature_reactance=self._per_unit(values[28]),
                stator_current_service_factor=self._float(values[29]),
                maximum_loading_angle=Angle(self._float(values[30]), "degree"),
                generator_type=self._number(values[31]),
                generator_unit_name=values[32],
            )
            self._metadata(generator, line_number, raw, values)
            result.append(generator)
        return result

    def _build_lines(self, rows: list[tuple[int, list[str], str]]) -> list[TransmissionLine]:
        result: list[TransmissionLine] = []
        for line_number, values, raw in rows:
            if len(values) < 7:
                continue
            line = TransmissionLine(
                name=values[17] or f"Line_{values[0]}_{values[1]}",
                from_bus_id=self._number(values[0]),
                to_bus_id=self._number(values[1]),
                circuit_identifier=values[2],
                from_bus=self._number(values[0]),
                to_bus=self._number(values[1]),
                line_circuit=values[2],
                r=self._float(values[3]),
                x=self._float(values[4]),
                rating=ApparentPower(self._float(values[6]), "MVA"),
                series_resistance=self._per_unit(values[3]),
                series_reactance=self._per_unit(values[4]),
                line_charging=ReactivePower(self._float(values[5]), "MVAr"),
                limit_1=ApparentPower(self._float(values[6]), "MVA"),
                limit_2=ApparentPower(self._float(values[7]), "MVA"),
                limit_3=ApparentPower(self._float(values[8]), "MVA"),
                from_breaker_status=self._number(values[9]),
                to_breaker_status=self._number(values[10]),
                line_length=Distance(self._float(values[11]), "km"),
                area_number=self._number(values[12]),
                owner_number=self._number(values[13]),
                zero_sequence_resistance=self._per_unit(values[14]),
                zero_sequence_reactance=self._per_unit(values[15]),
                zero_sequence_charging=self._per_unit(values[16]),
                branch_name=values[17],
            )
            self._metadata(line, line_number, raw, values)
            result.append(line)
        return result

    def _build_transformers(self, rows: list[tuple[int, list[str], str]]) -> list[Transformer]:
        result: list[Transformer] = []
        for line_number, values, raw in rows:
            if len(values) < 14 or (
                len(values) > 14 and re.fullmatch(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?", values[14])
            ):
                continue
            transformer = Transformer(
                name=f"Transformer_{values[0]}_{values[1]}",
                from_bus_id=self._number(values[0]),
                to_bus_id=self._number(values[1]),
                third_bus_id=self._number(values[2]),
                circuit_identifier=values[3],
                from_bus=self._number(values[0]),
                to_bus=self._number(values[1]),
                line_circuit=values[3],
                magnetizing_conductance=self._per_unit(values[4]),
                magnetizing_susceptance=self._per_unit(values[5]),
                winding_1_status=self._number(values[6]),
                winding_2_status=self._number(values[7]),
                winding_3_status=self._number(values[8]),
                star_point_voltage=self._per_unit(values[9]),
                branch_name=values[14] if len(values) > 14 else "",
            )
            self._metadata(transformer, line_number, raw, values)
            continuation_rows: list[list[str]] = []
            row_index = rows.index((line_number, values, raw)) + 1
            while row_index < len(rows):
                _, next_values, _ = rows[row_index]
                if len(next_values) < 20 or not next_values[0].isdigit():
                    break
                continuation_rows.append(next_values)
                row_index += 1
            if continuation_rows:
                transformer.ext["ntw_continuation_values"] = continuation_rows
                first_continuation = continuation_rows[0]
                transformer.r = Percentage(self._float(first_continuation[1]) * 100.0, "%")
                transformer.x = Percentage(self._float(first_continuation[2]) * 100.0, "%")
            result.append(transformer)
        return result

    def _build_shunts(self, rows: list[tuple[int, list[str], str]]) -> list[ShuntDevice]:
        result: list[ShuntDevice] = []
        for line_number, values, raw in rows:
            if len(values) < 6:
                continue
            shunt = ShuntDevice(
                name=f"Shunt_{values[0]}",
                bus_id=self._number(values[0]),
                control_mode=self._number(values[1]),
                voltage_maximum=self._per_unit(values[2]),
                voltage_minimum=self._per_unit(values[3]),
                controlled_bus_id=self._number(values[4]),
                initial_admittance=ReactivePower(self._float(values[5]), "MVAr"),
                status=self._number(values[6]) if len(values) > 6 else None,
            )
            for group in range(3):
                offset = 7 + group * 4
                if len(values) <= offset:
                    break
                setattr(shunt, f"element_{group + 1}_status", self._number(values[offset]))
                if len(values) > offset + 1:
                    setattr(shunt, f"element_{group + 1}_count", self._number(values[offset + 1]))
                if len(values) > offset + 2:
                    setattr(
                        shunt,
                        f"element_{group + 1}_size",
                        ReactivePower(self._float(values[offset + 2]), "MVAr"),
                    )
                if len(values) > offset + 3:
                    setattr(
                        shunt,
                        f"element_{group + 1}_zero_sequence_impedance",
                        self._per_unit(values[offset + 3]),
                    )
            self._metadata(shunt, line_number, raw, values)
            result.append(shunt)
        return result

    def _build_series_capacitors(
        self, rows: list[tuple[int, list[str], str]]
    ) -> list[SeriesCapacitor]:
        result: list[SeriesCapacitor] = []
        for line_number, values, raw in rows:
            if len(values) < 18:
                continue
            capacitor = SeriesCapacitor(
                name=values[17] or f"SeriesCapacitor_{values[0]}_{values[1]}",
                from_bus_id=self._number(values[0]),
                to_bus_id=self._number(values[1]),
                circuit_identifier=values[2],
                series_resistance=self._per_unit(values[3]),
                series_reactance=self._per_unit(values[4]),
                limit_1=ApparentPower(self._float(values[5]), "MVA"),
                limit_2=ApparentPower(self._float(values[6]), "MVA"),
                limit_3=ApparentPower(self._float(values[7]), "MVA"),
                from_shunt_status=self._number(values[8]),
                from_shunt_conductance=self._per_unit(values[9]),
                from_shunt_susceptance=self._per_unit(values[10]),
                to_shunt_status=self._number(values[11]),
                to_shunt_conductance=self._per_unit(values[12]),
                to_shunt_susceptance=self._per_unit(values[13]),
                from_breaker_status=self._number(values[14]),
                to_breaker_status=self._number(values[15]),
                owner_number=self._number(values[16]),
                branch_name=values[17],
            )
            self._metadata(capacitor, line_number, raw, values)
            result.append(capacitor)
        return result

    def _build_dc_links(self, rows: list[tuple[int, list[str], str]]) -> list[DCLink]:
        result: list[DCLink] = []
        for line_number, values, raw in rows:
            if (
                len(values) < 13
                or not self._is_integer(values[3])
                or not self._is_integer(values[9])
            ):
                continue
            link = DCLink(
                name=values[12] or f"DCLink_{values[0]}",
                pole_id=self._number(values[0]),
                area_number=self._number(values[1]),
                zone_number=self._number(values[2]),
                control_mode=self._number(values[3]),
                line_resistance=Resistance(self._float(values[4]), "ohm"),
                control_set_value=ActivePower(self._float(values[5]), "MW"),
                scheduled_voltage=Voltage(self._float(values[6]), "kV"),
                current_threshold_voltage=Voltage(self._float(values[7]), "kV"),
                current_margin=self._per_unit(values[8]),
                status=self._number(values[9]),
                nominal_voltage=Voltage(self._float(values[10]), "kV"),
                nominal_power=ActivePower(self._float(values[11]), "MW"),
                pole_name=values[12],
            )
            self._metadata(link, line_number, raw, values)
            result.append(link)
        return result

    def _build_impedance_corrections(
        self, rows: list[tuple[int, list[str], str]]
    ) -> list[ImpedanceCorrection]:
        return [
            ImpedanceCorrection(
                name=f"ImpedanceCorrection_{values[0]}",
                table_number=self._number(values[0]),
                tap_1=self._float(values[1]),
                correction_1=self._float(values[2]),
                tap_2=self._float(values[3]),
                correction_2=self._float(values[4]),
                tap_3=self._float(values[5]),
                correction_3=self._float(values[6]),
            )
            for _, values, _ in rows
            if len(values) >= 7
        ]

    def _build_line_mutual_impedances(
        self, rows: list[tuple[int, list[str], str]]
    ) -> list[LineMutualImpedance]:
        result = []
        for line_number, values, raw in rows:
            if len(values) < 12:
                continue
            item = LineMutualImpedance(
                name=f"LineMutualImpedance_{values[0]}_{values[5]}",
                line_1_from_bus=self._number(values[0]),
                line_1_to_bus=self._number(values[1]),
                line_1_circuit=values[2],
                line_1_start_percent=self._percentage(values[3]),
                line_1_end_percent=self._percentage(values[4]),
                line_2_from_bus=self._number(values[5]),
                line_2_to_bus=self._number(values[6]),
                line_2_circuit=values[7],
                line_2_start_percent=self._percentage(values[8]),
                line_2_end_percent=self._percentage(values[9]),
                mutual_resistance=self._per_unit(values[10]),
                mutual_reactance=self._per_unit(values[11]),
            )
            self._metadata(item, line_number, raw, values)
            result.append(item)
        return result

    def _build_induction_motors(
        self, rows: list[tuple[int, list[str], str]]
    ) -> list[InductionMotor]:
        return []

    def _build_breaker_configurations(
        self, rows: list[tuple[int, list[str], str]]
    ) -> list[BreakerConfiguration]:
        result = []
        for line_number, values, raw in rows:
            if values:
                item = BreakerConfiguration(
                    name=f"BreakerConfiguration_{values[0]}",
                    bus_number=self._number(values[0]),
                    node_1=values[1] if len(values) > 1 else None,
                    node_2=values[2] if len(values) > 2 else None,
                    node_3=values[3] if len(values) > 3 else None,
                    node_4=values[4] if len(values) > 4 else None,
                )
                self._metadata(item, line_number, raw, values)
                result.append(item)
        return result

    def _build_facts(self, rows: list[tuple[int, list[str], str]]) -> list[FACTSDevice]:
        result = []
        for line_number, values, raw in rows:
            if len(values) < 26:
                continue
            item = FACTSDevice(
                name=values[0],
                device_name=values[0],
                send_bus_id=self._number(values[1]),
                terminal_bus_id=self._number(values[2]),
                circuit_identifier=values[3],
                device_type=self._number(values[4]),
                active_reference=ActivePower(self._float(values[5]), "MW"),
                reactive_reference=ReactivePower(self._float(values[6]), "MVAr"),
                voltage_reference=self._per_unit(values[7]),
                maximum_shunt_current=ApparentPower(self._float(values[8]), "MVA"),
                maximum_power_transfer=ActivePower(self._float(values[9]), "MW"),
                terminal_voltage_minimum=self._per_unit(values[10]),
                terminal_voltage_maximum=self._per_unit(values[11]),
                series_voltage_maximum=self._per_unit(values[12]),
                series_voltage_minimum=self._per_unit(values[13]),
                series_current_maximum=self._per_unit(values[14]),
                series_current_emergency=self._per_unit(values[15]),
                series_current_minimum=self._per_unit(values[16]),
                series_reactance=self._per_unit(values[17]),
                droop=self._per_unit(values[18]),
                status=self._number(values[24]),
                owner_number=self._number(values[25]),
            )
            self._metadata(item, line_number, raw, values)
            result.append(item)
        return result

    def _build_owners(self, rows: list[tuple[int, list[str], str]]) -> list[Owner]:
        return [
            Owner(
                name=values[1] or f"Owner_{values[0]}",
                owner_number=self._number(values[0]),
                owner_name=values[1],
            )
            for _, values, _ in rows
            if len(values) >= 2
        ]

    @staticmethod
    def _add_all(system: AnaredeSystem, components: list[Component] | list[Any]) -> None:
        for component in components:
            system.add_component(component)

    def _add_components(
        self,
        system: AnaredeSystem,
        grouped: dict[str, list[Component]],
        block: str,
        components: list[Component] | list[Any],
    ) -> None:
        grouped[block] = components
        self._add_all(system, components)
        self._log_block_progress(block, grouped)

    @staticmethod
    def _add_areas(
        system: AnaredeSystem,
        grouped: dict[str, list[Component]],
        buses: list[ACBus],
        areas: dict[int, Area],
    ) -> None:
        for bus in buses:
            area = bus.area
            area_number = area.area_number if isinstance(area, Area) and area.area_number else 1
            area = areas.setdefault(
                area_number, Area(name=f"Area_{area_number}", area_number=area_number)
            )
            bus.area = area
        grouped["DARE"] = list(areas.values())
        for area in areas.values():
            system.add_component(area)
        NtwFileParser._log_block_progress("DARE", grouped)

    @staticmethod
    def _metadata(component: Any, line_number: int, raw: str, values: list[str]) -> None:
        component.ext["ntw_line_number"] = line_number
        component.ext["ntw_raw"] = raw
        component.ext["ntw_values"] = values

    @staticmethod
    def _float(value: str) -> float:
        return float(value.replace("D", "E").replace("d", "e"))

    @classmethod
    def _per_unit(cls, value: str) -> PerUnit:
        return PerUnit(cls._float(value), "pu")

    @classmethod
    def _percentage(cls, value: str) -> Percentage:
        return Percentage(cls._float(value), "percent")

    @classmethod
    def _number(cls, value: str) -> int | float:
        number = cls._float(value)
        return int(number) if number == int(number) else number

    @classmethod
    def _is_integer(cls, value: str) -> bool:
        number = cls._float(value)
        return number == int(number)
