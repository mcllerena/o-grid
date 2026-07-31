"""ANAREDE parser and in-memory conversion to infrasys System."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from infrasys import Component, System
from loguru import logger

from o_grid.constants import REQUIRED_KEYS
from o_grid.models import (
    BLOCK_BASE_CLASSES,
    ACBus,
    AnaredeComponent,
    Arc,
    Area,
    BusShuntBank,
    BusVoltageMonitoring,
    DCBus,
    DCLine,
    FromToToFrom,
    Generator,
    GenType,
    LineShuntBank,
    MinMax,
    VoltageBaseGroup,
    VoltageMonitoringCondition,
)
from o_grid.system import AnaredeSystem
from o_grid.units import (
    ActivePower,
    ApparentPower,
    Percentage,
    ReactivePower,
    Voltage,
    get_magnitude,
)
from o_grid.utils.utils_parser import (
    ParsedScalar,
    attach_raw_component_metadata,
    coerce_circuit_number,
    component_name,
    default_dcli_circuit,
    has_non_default_tap,
    has_non_zero_angle,
    load_mapping,
    looks_numeric,
    map_anarede_state_to_available,
    model_field_name,
    normalize_dbar_values,
    normalize_dcba_values,
    normalize_dccv_values,
    normalize_dcli_values,
    normalize_dcnv_values,
    normalize_delo_values,
    normalize_dger_values,
    normalize_dlin_values,
    normalize_dshl_values,
    normalize_group_key,
    normalize_row,
    parse_fixed_value,
    parse_numeric,
    read_pwf_text,
    repair_dbar_values,
    slice_field,
)

MAPPING_PATH = Path(__file__).resolve().parent / "config" / "anarede_mapping.json"
GEN_TYPE_MAPPING_PATH = Path(__file__).resolve().parent / "config" / "gen_type_mapping.json"

DLIN_DERIVED_BLOCKS: tuple[str, ...] = ("DLIN_TAP", "DLIN_PHASE_SHIFT")
BUS_INTERNAL_GROUP_BLOCKS: tuple[str, ...] = ("DGBT", "DGLT")


@dataclass(slots=True)
class ParsedAnaredeSystem:
    """Parsed ANAREDE representation and populated infrasys system."""

    source: Path
    system: System
    components_by_block: dict[str, list[Component]]
    component_classes: dict[str, type[Component]]


class AnaredeInfrasysParser:
    """Parse ANAREDE `.pwf` files and populate an infrasys `System`."""

    def __init__(
        self,
        mapping_path: Path | str = MAPPING_PATH,
        system_name: str = "ANAREDE",
        gen_type_mapping_path: Path | str = GEN_TYPE_MAPPING_PATH,
    ) -> None:
        self.mapping_path = Path(mapping_path)
        self.system_name = system_name
        self.gen_type_mapping_path = Path(gen_type_mapping_path)
        self._gen_type_by_bus = self._load_gen_type_mapping(self.gen_type_mapping_path)
        self._raw_mapping = load_mapping(self.mapping_path)
        self.mapping = {
            section: spec
            for section, spec in self._raw_mapping.items()
            if not section.startswith("_")
        }
        self.component_classes = self._build_component_classes(self.mapping)
        dlin_fields = self.mapping.get("DLIN", {}).get("fields", {})
        if dlin_fields:
            for block in DLIN_DERIVED_BLOCKS:
                self.component_classes[block] = self._create_component_class(block, dlin_fields)
        self.dbsh_bank_fields = self.mapping.get("DBSH", {}).get("bank_fields", {})
        if self.dbsh_bank_fields:
            self.component_classes["DBSH_BANK"] = self._create_component_class(
                "DBSH_BANK", self.dbsh_bank_fields
            )

    def _build_component_classes(self, mapping: dict[str, Any]) -> dict[str, type[Component]]:
        classes: dict[str, type[Component]] = {}
        for block, spec in mapping.items():
            base_class = BLOCK_BASE_CLASSES.get(block)
            if base_class is not None:
                classes[block] = base_class
                continue
            classes[block] = self._create_component_class(block, spec.get("fields", {}))
        return classes

    def _create_component_class(self, block: str, field_specs: dict[str, Any]) -> type[Component]:
        base_class = BLOCK_BASE_CLASSES.get(block, AnaredeComponent)
        class_name = (
            base_class.__name__ if base_class is not AnaredeComponent else f"Anarede{block}"
        )
        annotations: dict[str, Any] = {}
        namespace: dict[str, Any] = {
            "__module__": __name__,
            "__annotations__": annotations,
            "block": block,
        }
        base_annotations: dict[str, Any] = getattr(base_class, "__annotations__", {})

        if block not in DLIN_DERIVED_BLOCKS:
            for field_name in field_specs:
                if block == "DBSH_BANK" and field_name in {"operation", "state"}:
                    # These are represented by the availability flag on the shunt bank.
                    continue
                model_attr_name = model_field_name(block, field_name)
                if model_attr_name in base_annotations or hasattr(base_class, model_attr_name):
                    # Keep strongly-typed model fields declared on the concrete base class.
                    continue
                annotations[model_attr_name] = ParsedScalar
                namespace[model_attr_name] = None

        if block == "DBSH_BANK":
            annotations["parent_record_index"] = int | None
            namespace["parent_record_index"] = None

        component_class = type(class_name, (base_class,), namespace)
        component_class.block = block
        return component_class

    def _to_model_values(
        self, block: str, values: Mapping[str, ParsedScalar]
    ) -> dict[str, ParsedScalar]:
        return {model_field_name(block, field_name): value for field_name, value in values.items()}

    def parse(self, pwf_path: Path | str) -> ParsedAnaredeSystem:
        source = Path(pwf_path)
        lines = read_pwf_text(source).splitlines()
        system = AnaredeSystem(name=self.system_name)
        title_lines: list[str] = []
        components_by_block: dict[str, list[Component]] = {
            block: [] for block in self.component_classes
        }

        active_block: str | None = None
        current_dbsh_parent_index: int | None = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            section_header = self._section_header_name(stripped)
            if section_header is not None:
                active_block = section_header
                current_dbsh_parent_index = None
                continue

            if active_block is None:
                continue
            if stripped.startswith("("):
                continue

            upper = stripped.upper()
            if upper == "FIM":
                break
            if upper.startswith("99999"):
                if active_block == "DBAR":
                    self._attach_bus_areas(system, components_by_block)
                if active_block is not None:
                    self._log_block_progress(active_block, components_by_block)
                active_block = None
                current_dbsh_parent_index = None
                continue

            if active_block == "DBSH" and upper == "FBAN":
                current_dbsh_parent_index = None
                continue

            if active_block == "TITU":
                title_line = self._parse_titu_line(line)
                if title_line:
                    title_lines.append(title_line)
                continue

            if active_block in {"DOPC", "DCTE"}:
                for record in self._parse_pair_records(active_block, line, components_by_block):
                    components_by_block[active_block].append(record)
                    self._add_component(system, record)
                continue

            if (
                active_block == "DBSH"
                and current_dbsh_parent_index is not None
                and "DBSH_BANK" in self.component_classes
            ):
                controller = components_by_block["DBSH"][current_dbsh_parent_index - 1]
                bank_record = self._parse_bank_record(
                    line,
                    len(components_by_block["DBSH_BANK"]) + 1,
                    parent_record_index=current_dbsh_parent_index,
                    controller=controller,
                )
                components_by_block["DBSH_BANK"].append(bank_record)
                self._add_component(system, bank_record)
                # Attach the controller after adding so it is not registered as a
                # standalone top-level component in the system.
                object.__setattr__(bank_record, "bank_controller", controller)
                continue

            record = self._parse_record(
                active_block, line, len(components_by_block[active_block]) + 1
            )
            components_by_block[active_block].append(record)

            # Keep group dictionaries internal; they are attached to ACBus records later.
            if active_block == "DLIN":
                arc = self._build_arc_from_dlin_record(record, len(components_by_block["DLIN"]))
                setattr(record, "arc", arc)
                self._add_component(system, arc)

            if active_block not in BUS_INTERNAL_GROUP_BLOCKS and active_block not in (
                "DBAR",
                "DBSH",
                "DELO",
                "DMFL_CIRC",
                "DMTE",
                "DTPF_CIRC",
            ):
                if active_block != "DLIN" or not self._is_transformer_dlin_record(record):
                    self._add_component(system, record)

            if active_block == "DLIN":
                for derived in self._derive_transformer_records_from_line(
                    record,
                    components_by_block,
                ):
                    self._add_component(system, derived)

            if active_block == "DBSH":
                current_dbsh_parent_index = len(components_by_block["DBSH"])

        if title_lines:
            system.description = "\n".join(title_lines)

        self._attach_bus_voltage_groups(components_by_block)
        self._attach_area_generation_peaks(components_by_block)
        self._attach_area_interchange_areas(components_by_block)
        self._attach_dcsc_owner_areas(components_by_block)
        self._attach_dlin_owner_areas(components_by_block)
        self._assign_dcli_circuit_defaults(components_by_block)
        self._attach_delo_power_base_defaults(components_by_block)
        self._attach_generator_active_power(components_by_block)
        self._attach_generator_types(components_by_block)
        self._attach_component_bus_references(components_by_block)
        self._attach_dc_bus_references(components_by_block)
        self._embed_dc_line_data(components_by_block)
        self._attach_ctap_options(components_by_block)
        self._attach_flow_monitoring(components_by_block)
        self._attach_bus_voltage_monitoring(system, components_by_block)
        self._rename_dcli_components(components_by_block)
        self._attach_dlin_branch_electrical_values(components_by_block)
        self._rename_dlin_components(components_by_block)
        total = sum(1 for _ in system._component_mgr.iter_all())
        logger.success("Successfully parsed {} component(s).", total)

        return ParsedAnaredeSystem(
            source=source,
            system=system,
            components_by_block={k: v for k, v in components_by_block.items() if v},
            component_classes=self.component_classes,
        )

    def _add_component(self, system: System, component: Component) -> None:
        system.add_component(component)

    def _log_block_progress(
        self, block: str, components_by_block: dict[str, list[Component]]
    ) -> None:
        count = len(components_by_block.get(block, []))
        if count:
            logger.info("Parsed {} section: {} record(s)", block, count)

    def _attach_bus_areas(
        self, system: System, components_by_block: dict[str, list[Component]]
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        areas_by_key: dict[str, Area] = {}
        for bus in buses:
            area_value = getattr(bus, "area", None)
            area_key = normalize_group_key(area_value)
            if not area_key:
                continue

            area = areas_by_key.get(area_key)
            area_number = int(float(area_key)) if looks_numeric(area_key) else None
            if area is None:
                area = Area(name=f"Area_{area_key}", area_number=area_number)
                areas_by_key[area_key] = area
                self._add_component(system, area)

            setattr(bus, "area", area)
            self._add_component(system, bus)
            if area_number is None:
                logger.warning("Bus {} references a non-numeric area key {}", bus.name, area_key)

    def _build_arc_from_dlin_record(self, line_record: AnaredeComponent, record_index: int) -> Arc:
        from_bus = getattr(line_record, "from_bus", None)
        to_bus = getattr(line_record, "to_bus", None)
        return Arc(
            name=f"Arc_{record_index}",
            from_to=from_bus,
            to_from=to_bus,
        )

    def _attach_dcsc_owner_areas(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        buses = components_by_block.get("DBAR")
        csc_records = components_by_block.get("DCSC")
        if not buses or not csc_records:
            return

        buses_by_number = {normalize_group_key(getattr(bus, "number", None)): bus for bus in buses}
        for csc in csc_records:
            csc_ext = getattr(csc, "ext", None)
            if not isinstance(csc_ext, dict):
                continue
            owner_token = str(csc_ext.pop("owner_token", "")).strip().upper()
            bus_attr = "from_bus" if owner_token == "F" else "to_bus"
            bus_number = getattr(csc, bus_attr, None)
            bus_key = normalize_group_key(bus_number)
            owner_bus = buses_by_number.get(bus_key)
            owner_area = getattr(owner_bus, "area", None) if owner_bus is not None else None
            setattr(csc, "owner", owner_area)

    def _attach_dlin_owner_areas(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        buses_by_number = {normalize_group_key(getattr(bus, "number", None)): bus for bus in buses}
        for block in ("DLIN", "DLIN_TAP", "DLIN_PHASE_SHIFT"):
            for line in components_by_block.get(block, []):
                line_ext = getattr(line, "ext", None)
                if not isinstance(line_ext, dict):
                    continue
                owner_token = str(line_ext.pop("owner_token", "")).strip().upper()
                if owner_token not in {"F", "T"}:
                    continue

                bus_attr = "from_bus" if owner_token == "F" else "to_bus"
                bus_number = getattr(line, bus_attr, None)
                bus_key = normalize_group_key(bus_number)
                owner_bus = buses_by_number.get(bus_key)
                owner_area = getattr(owner_bus, "area", None) if owner_bus is not None else None
                setattr(line, "owner", owner_area)

    def _attach_area_generation_peaks(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        areas_by_id: dict[int, Area] = {}
        active_totals: dict[int, float] = {}
        reactive_totals: dict[int, float] = {}
        for bus in buses:
            area = getattr(bus, "area", None)
            if isinstance(area, Area):
                area_id = id(area)
                areas_by_id[area_id] = area
                active_totals.setdefault(area_id, 0.0)
                reactive_totals.setdefault(area_id, 0.0)

        for bus in buses:
            area = getattr(bus, "area", None)
            if not isinstance(area, Area):
                continue

            area_id = id(area)
            active_generation = getattr(bus, "active_generation", None)
            reactive_generation = getattr(bus, "reactive_generation", None)
            active_totals[area_id] += (
                float(get_magnitude(active_generation)) if active_generation is not None else 0.0
            )
            reactive_totals[area_id] += (
                float(get_magnitude(reactive_generation))
                if reactive_generation is not None
                else 0.0
            )

        for area_id, area in areas_by_id.items():
            object.__setattr__(area, "peak_active_power", ActivePower(active_totals[area_id], "MW"))
            object.__setattr__(
                area,
                "peak_reactive_power",
                ReactivePower(reactive_totals[area_id], "MVAr"),
            )

    def _attach_area_interchange_areas(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        buses = components_by_block.get("DBAR")
        interchanges = components_by_block.get("DARE")
        if not buses or not interchanges:
            return

        areas_by_key: dict[str, Area] = {}
        for bus in buses:
            area = getattr(bus, "area", None)
            if isinstance(area, Area):
                areas_by_key.setdefault(normalize_group_key(area), area)

        for interchange in interchanges:
            interchange_ext = getattr(interchange, "ext", None)
            if not isinstance(interchange_ext, dict):
                continue
            area_token = interchange_ext.pop("area_token", None)
            if area_token is None:
                continue
            area = areas_by_key.get(normalize_group_key(area_token))
            if area is not None:
                object.__setattr__(interchange, "area", area)

    @staticmethod
    def _branch_bus_key(value: object) -> str:
        number = getattr(value, "number", None)
        target = number if number is not None else value
        return normalize_group_key(cast("ParsedScalar", target))

    def _attach_ctap_options(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        circuit_records = components_by_block.get("DTPF_CIRC")
        if not circuit_records:
            return

        selected: set[tuple[str, str, str]] = set()
        for record in circuit_records:
            for index in range(1, 6):
                from_key = normalize_group_key(getattr(record, f"from_bus_{index}", None))
                to_key = normalize_group_key(getattr(record, f"to_bus_{index}", None))
                circuit_key = normalize_group_key(getattr(record, f"circuit_{index}", None))
                if not from_key or not to_key:
                    continue
                selected.add((from_key, to_key, circuit_key))
                selected.add((to_key, from_key, circuit_key))

        if not selected:
            return

        for block in ("DLIN", "DLIN_TAP", "DLIN_PHASE_SHIFT"):
            for branch in components_by_block.get(block, []):
                from_key = self._branch_bus_key(getattr(branch, "from_bus", None))
                to_key = self._branch_bus_key(getattr(branch, "to_bus", None))
                circuit_key = normalize_group_key(getattr(branch, "line_circuit", None))
                if (from_key, to_key, circuit_key) in selected:
                    object.__setattr__(branch, "ctap_option", True)

    def _attach_flow_monitoring(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        circuit_records = components_by_block.get("DMFL_CIRC")
        if not circuit_records:
            return

        selected: set[tuple[str, str, str]] = set()
        for record in circuit_records:
            for index in range(1, 6):
                from_key = normalize_group_key(getattr(record, f"from_bus_{index}", None))
                to_key = normalize_group_key(getattr(record, f"to_bus_{index}", None))
                circuit_key = normalize_group_key(getattr(record, f"circuit_{index}", None))
                if not from_key or not to_key:
                    continue
                selected.add((from_key, to_key, circuit_key))
                selected.add((to_key, from_key, circuit_key))

        if not selected:
            return

        for block in ("DLIN", "DLIN_TAP", "DLIN_PHASE_SHIFT"):
            for branch in components_by_block.get(block, []):
                from_key = self._branch_bus_key(getattr(branch, "from_bus", None))
                to_key = self._branch_bus_key(getattr(branch, "to_bus", None))
                circuit_key = normalize_group_key(getattr(branch, "line_circuit", None))
                if (from_key, to_key, circuit_key) in selected:
                    object.__setattr__(branch, "flow_monitoring", True)

    @staticmethod
    def _voltage_kv_key(value: object) -> str:
        magnitude = get_magnitude(value) if hasattr(value, "magnitude") else value
        return normalize_group_key(cast("ParsedScalar", magnitude))

    @staticmethod
    def _monitoring_condition(token: object) -> VoltageMonitoringCondition | None:
        if token is None:
            return None
        key = str(token).strip().upper()
        try:
            return VoltageMonitoringCondition(key)
        except ValueError:
            return None

    def _resolve_voltage_base_group(
        self,
        element_id: object,
        voltage_groups_by_kv: dict[str, VoltageBaseGroup],
    ) -> VoltageBaseGroup | None:
        kv_key = self._voltage_kv_key(element_id)
        if not looks_numeric(kv_key):
            return None
        group = voltage_groups_by_kv.get(kv_key)
        if group is None:
            group = VoltageBaseGroup(
                name=f"VoltageBase_{kv_key}",
                voltage=Voltage(float(kv_key), "kV"),
            )
            voltage_groups_by_kv[kv_key] = group
        return group

    def _resolve_monitoring_element(
        self,
        element_type: object,
        element_id: object,
        buses_by_number: dict[str, ACBus],
        areas_by_key: dict[str, Area],
        voltage_groups_by_kv: dict[str, VoltageBaseGroup],
    ) -> ACBus | Area | VoltageBaseGroup | None:
        if element_type is None:
            return None
        type_key = str(element_type).strip().upper()
        if not type_key:
            return None
        if type_key == "BARR":
            return buses_by_number.get(normalize_group_key(cast("ParsedScalar", element_id)))
        if type_key == "AREA":
            return areas_by_key.get(normalize_group_key(cast("ParsedScalar", element_id)))
        if type_key == "TENS":
            return self._resolve_voltage_base_group(element_id, voltage_groups_by_kv)
        return None

    def _attach_bus_voltage_monitoring(
        self,
        system: System,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        records = components_by_block.get("DMTE")
        if not records:
            return

        buses = components_by_block.get("DBAR", [])
        buses_by_number: dict[str, ACBus] = {
            normalize_group_key(getattr(bus, "number", None)): cast(ACBus, bus) for bus in buses
        }
        areas_by_key: dict[str, Area] = {}
        for bus in buses:
            area = getattr(bus, "area", None)
            if isinstance(area, Area):
                areas_by_key.setdefault(normalize_group_key(area), area)

        # Reuse voltage base groups already declared by DGBT, keyed by their kV value,
        # and lazily create any monitored base voltage that is not yet defined.
        voltage_groups_by_kv: dict[str, VoltageBaseGroup] = {}
        for group in components_by_block.get("DGBT", []):
            kv_key = self._voltage_kv_key(getattr(group, "voltage", None))
            if looks_numeric(kv_key):
                voltage_groups_by_kv.setdefault(kv_key, cast(VoltageBaseGroup, group))

        operator_slots: tuple[tuple[int, str | None], ...] = (
            (1, "condition_1"),
            (2, "main_condition"),
            (3, "condition_2"),
            (4, None),
        )

        for record in records:
            monitored: list[ACBus | Area | VoltageBaseGroup] = []
            conditions: list[VoltageMonitoringCondition | None] = []
            for index, operator_field in operator_slots:
                element = self._resolve_monitoring_element(
                    getattr(record, f"element_type_{index}", None),
                    getattr(record, f"element_id_{index}", None),
                    buses_by_number,
                    areas_by_key,
                    voltage_groups_by_kv,
                )
                if element is None:
                    continue
                monitored.append(element)
                operator_token = getattr(record, operator_field, None) if operator_field else None
                conditions.append(self._monitoring_condition(operator_token))

            if not monitored:
                continue

            # Add the monitoring set with empty references first, then attach the
            # resolved elements via object.__setattr__ so infrasys does not recurse
            # into the bus graph (buses hold internal, unattached voltage groups).
            monitoring = BusVoltageMonitoring(name=getattr(record, "name", "BusVoltageMonitoring"))
            self._add_component(system, monitoring)
            object.__setattr__(monitoring, "type", monitored)
            object.__setattr__(monitoring, "condition", conditions)

    def _attach_component_bus_references(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        buses_by_number = {normalize_group_key(getattr(bus, "number", None)): bus for bus in buses}
        for components in components_by_block.values():
            for component in components:
                is_dc_link = isinstance(component, DCLine)
                for bus_field in (
                    "bus",
                    "from_bus",
                    "to_bus",
                    "extremity_bus",
                    "measurement_terminal",
                    "controlled_bus",
                    "ac_bus",
                ):
                    if is_dc_link and bus_field in ("from_bus", "to_bus"):
                        continue
                    bus_value = getattr(component, bus_field, None)
                    if bus_value is None or isinstance(bus_value, ACBus):
                        continue
                    bus_key = normalize_group_key(bus_value)
                    bus_component = buses_by_number.get(bus_key)
                    if bus_component is not None:
                        object.__setattr__(component, bus_field, bus_component)

                if isinstance(component, Generator):
                    number_value = getattr(component, "number", None)
                    if number_value is not None and not isinstance(number_value, ACBus):
                        bus_component = buses_by_number.get(normalize_group_key(number_value))
                        if isinstance(bus_component, ACBus):
                            object.__setattr__(component, "number", bus_component)

                component_ext = getattr(component, "ext", None)
                if not isinstance(component_ext, dict):
                    continue

                controlled_bus_token = component_ext.pop("controlled_bus_token", None)
                if controlled_bus_token is not None:
                    resolved_controlled_bus = self._resolve_controlled_bus(
                        controlled_bus_token,
                        component,
                        buses_by_number,
                    )
                    if resolved_controlled_bus is not None:
                        object.__setattr__(component, "controlled_bus", resolved_controlled_bus)

                measurement_terminal_token = component_ext.pop("measurement_terminal_token", None)
                if measurement_terminal_token is not None:
                    bus_key = normalize_group_key(measurement_terminal_token)
                    bus_component = buses_by_number.get(bus_key)
                    if isinstance(bus_component, ACBus):
                        object.__setattr__(component, "measurement_terminal", bus_component)

                arc = getattr(component, "arc", None)
                if isinstance(arc, Arc):
                    from_bus = getattr(component, "from_bus", None)
                    to_bus = getattr(component, "to_bus", None)
                    if isinstance(from_bus, ACBus):
                        object.__setattr__(arc, "from_to", from_bus)
                    if isinstance(to_bus, ACBus):
                        object.__setattr__(arc, "to_from", to_bus)

    def _attach_dc_bus_references(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        dc_buses = components_by_block.get("DCBA")
        if not dc_buses:
            return

        dc_buses_by_number = {
            normalize_group_key(getattr(bus, "number", None)): bus for bus in dc_buses
        }
        for components in components_by_block.values():
            for component in components:
                dc_bus_fields = ("dc_bus", "neutral_bus")
                if isinstance(component, DCLine):
                    dc_bus_fields = ("from_bus", "to_bus", "dc_bus", "neutral_bus")
                for bus_field in dc_bus_fields:
                    bus_value = getattr(component, bus_field, None)
                    if bus_value is None or isinstance(bus_value, DCBus):
                        continue
                    bus_key = normalize_group_key(bus_value)
                    bus_component = dc_buses_by_number.get(bus_key)
                    if isinstance(bus_component, DCBus):
                        object.__setattr__(component, bus_field, bus_component)

    def _rename_dcli_components(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        for link in components_by_block.get("DCLI", []):
            from_bus = getattr(link, "from_bus", None)
            to_bus = getattr(link, "to_bus", None)
            if not isinstance(from_bus, DCBus) or not isinstance(to_bus, DCBus):
                continue

            from_name = str(getattr(from_bus, "name", "")).strip()
            to_name = str(getattr(to_bus, "name", "")).strip()
            if not from_name or not to_name:
                continue

            tokens = [from_name, to_name]
            polarity = getattr(from_bus, "polarity", None)
            pole = "" if polarity is None else str(polarity).strip()
            if pole:
                tokens.append(pole)
            object.__setattr__(link, "name", "_".join(tokens))

    def _assign_dcli_circuit_defaults(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        dc_lines = components_by_block.get("DCLI")
        if not dc_lines:
            return

        circuits_by_pair: dict[tuple[str, str], set[int]] = {}
        for link in dc_lines:
            link_ext = getattr(link, "ext", None)
            pwf_values = link_ext.get("pwf_values", {}) if isinstance(link_ext, dict) else {}
            from_key = normalize_group_key(
                pwf_values.get("from_bus", getattr(link, "from_bus", None))
            )
            to_key = normalize_group_key(pwf_values.get("to_bus", getattr(link, "to_bus", None)))
            existing = circuits_by_pair.setdefault((from_key, to_key), set())

            circuit_number = coerce_circuit_number(getattr(link, "dcli_circuit", None))
            if circuit_number is None:
                circuit_number = default_dcli_circuit(pwf_values.get("operation"), existing)
                object.__setattr__(link, "dcli_circuit", circuit_number)
            existing.add(circuit_number)

    def _embed_dc_line_data(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        """Embed each DELO link record inside its matching DCLI line by DC link number."""
        dc_links = components_by_block.get("DELO")
        dc_lines = components_by_block.get("DCLI")
        if not dc_links or not dc_lines:
            return

        links_by_number = {
            normalize_group_key(getattr(link, "number", None)): link for link in dc_links
        }
        for line in dc_lines:
            link_number: object = None
            for bus_field in ("from_bus", "to_bus"):
                bus = getattr(line, bus_field, None)
                if isinstance(bus, DCBus):
                    link_number = getattr(bus, "dc_link_number", None)
                    if link_number is not None:
                        break
            link = links_by_number.get(normalize_group_key(link_number))
            if link is not None:
                object.__setattr__(line, "line_data", link)

    def _attach_delo_power_base_defaults(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        dc_links = components_by_block.get("DELO")
        if not dc_links:
            return

        dase = self._resolve_dase_power_base(components_by_block)
        for link in dc_links:
            if getattr(link, "power_base", None) is None:
                object.__setattr__(link, "power_base", dase)

    @staticmethod
    def _resolve_dase_power_base(
        components_by_block: dict[str, list[Component]],
    ) -> ActivePower:
        for constant in components_by_block.get("DCTE", []):
            mnemonic = str(getattr(constant, "mnemonic", "") or "").strip().upper()
            if mnemonic == "DASE":
                value = getattr(constant, "value", None)
                if value is not None:
                    return ActivePower(float(get_magnitude(value)), "MW")
        # ANAREDE default DC system power base when DASE is not declared.
        return ActivePower(100.0, "MW")

    def _attach_generator_active_power(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        generators = components_by_block.get("DGER")
        buses = components_by_block.get("DBAR")
        if not generators or not buses:
            return

        buses_by_number = {normalize_group_key(getattr(bus, "number", None)): bus for bus in buses}
        for generator in generators:
            bus = buses_by_number.get(normalize_group_key(getattr(generator, "number", None)))
            if bus is None:
                continue
            active_generation = getattr(bus, "active_generation", None)
            if active_generation is not None:
                object.__setattr__(generator, "active_generation", active_generation)

    @staticmethod
    def _load_gen_type_mapping(path: Path) -> dict[str, GenType]:
        if not path.exists():
            return {}
        index: dict[str, GenType] = {}
        for entry in load_mapping(path).values():
            number = entry.get("number")
            type_value = entry.get("type")
            if number is None or type_value is None:
                continue
            try:
                index[normalize_group_key(number)] = GenType(str(type_value))
            except ValueError:
                logger.warning("Unknown generator type '{}' for bus {}", type_value, number)
        return index

    def _attach_generator_types(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        generators = components_by_block.get("DGER")
        if not generators or not self._gen_type_by_bus:
            return

        for generator in generators:
            gen_type = self._gen_type_by_bus.get(
                normalize_group_key(getattr(generator, "number", None))
            )
            if gen_type is not None:
                object.__setattr__(generator, "gen_type", gen_type)

    def _resolve_controlled_bus(
        self,
        token: ParsedScalar,
        component: Component,
        buses_by_number: dict[str, Component],
    ) -> ACBus | None:
        from_bus = getattr(component, "from_bus", None)
        to_bus = getattr(component, "to_bus", None)

        if isinstance(token, str):
            normalized = token.strip().upper().replace("_", " ")
            if normalized == "FROM BUS":
                return from_bus if isinstance(from_bus, ACBus) else None
            if normalized == "TO BUS":
                return to_bus if isinstance(to_bus, ACBus) else None
            if not normalized:
                return from_bus if isinstance(from_bus, ACBus) else None

        value = get_magnitude(token)
        if isinstance(value, str):
            text = value.strip()
            if not looks_numeric(text):
                return from_bus if isinstance(from_bus, ACBus) else None
            numeric_value = float(text)
        elif isinstance(value, (int, float)):
            numeric_value = float(value)
        else:
            return from_bus if isinstance(from_bus, ACBus) else None

        abs_key = normalize_group_key(abs(numeric_value))
        abs_bus = buses_by_number.get(abs_key)
        if numeric_value < 0 and isinstance(to_bus, ACBus):
            if normalize_group_key(getattr(to_bus, "number", None)) == abs_key:
                return to_bus
        if numeric_value >= 0 and isinstance(from_bus, ACBus):
            if normalize_group_key(getattr(from_bus, "number", None)) == abs_key:
                return from_bus
        return abs_bus if isinstance(abs_bus, ACBus) else None

    def _rename_dlin_components(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        for block in ("DLIN", "DLIN_TAP", "DLIN_PHASE_SHIFT"):
            for line in components_by_block.get(block, []):
                from_bus = getattr(line, "from_bus", None)
                to_bus = getattr(line, "to_bus", None)
                line_circuit = getattr(line, "line_circuit", None)
                if not isinstance(from_bus, ACBus) or not isinstance(to_bus, ACBus):
                    continue

                from_name = str(getattr(from_bus, "name", "")).strip()
                to_name = str(getattr(to_bus, "name", "")).strip()
                circuit = "" if line_circuit is None else str(line_circuit).strip()
                if not from_name or not to_name:
                    continue

                tokens = [from_name, to_name]
                if circuit:
                    tokens.append(circuit)
                object.__setattr__(line, "name", "_".join(tokens))

    def _is_transformer_dlin_record(self, record: AnaredeComponent) -> bool:
        values = self._extract_dlin_values(record)
        return has_non_default_tap(values.get("tap")) or has_non_zero_angle(
            values.get("phase_shift")
        )

    def _attach_bus_voltage_groups(self, components_by_block: dict[str, list[Component]]) -> None:
        buses = components_by_block.get("DBAR")
        if not buses:
            return

        base_by_group = self._group_components_by_key(components_by_block.get("DGBT", []))
        limit_by_group = self._group_components_by_key(components_by_block.get("DGLT", []))

        for bus in buses:
            base_key = normalize_group_key(getattr(bus, "voltage_base_group", None))
            base_group = base_by_group.get(base_key)
            object.__setattr__(bus, "voltage_base_group", base_group)
            if base_group is not None:
                voltage = getattr(base_group, "voltage", None)
                setattr(
                    bus,
                    "base_voltage",
                    voltage if isinstance(voltage, Voltage) else Voltage(voltage, "kV"),
                )

            limit_key = normalize_group_key(getattr(bus, "voltage_limit_group", None))
            limit_group = limit_by_group.get(limit_key)
            object.__setattr__(bus, "voltage_limit_group", limit_group)
            if limit_group is not None:
                minimum_voltage_limit = getattr(limit_group, "minimum_voltage_limit", None)
                maximum_voltage_limit = getattr(limit_group, "maximum_voltage_limit", None)
                setattr(
                    bus,
                    "voltage_limits",
                    MinMax(
                        min=(
                            float(get_magnitude(minimum_voltage_limit))
                            if minimum_voltage_limit is not None
                            else 0.0
                        ),
                        max=(
                            float(get_magnitude(maximum_voltage_limit))
                            if maximum_voltage_limit is not None
                            else 0.0
                        ),
                    ),
                )

    def _group_components_by_key(self, components: list[Component]) -> dict[str, Component]:
        grouped: dict[str, Component] = {}
        for component in components:
            key = normalize_group_key(getattr(component, "group", None))
            if key:
                grouped[key] = component
        return grouped

    def _parse_record(self, block: str, line: str, record_index: int) -> AnaredeComponent:
        field_specs = self.mapping[block].get("fields", {})
        values = {
            name: parse_fixed_value(slice_field(line, spec), spec)
            for name, spec in field_specs.items()
        }
        raw_values: dict[str, ParsedScalar] = dict(values)
        owner_token: ParsedScalar = None
        controlled_bus_token: ParsedScalar = None
        measurement_terminal_token: ParsedScalar = None
        if block == "DBAR":
            values = repair_dbar_values(line, field_specs, values)
            values = normalize_dbar_values(values)
        if block == "DCBA":
            values = normalize_dcba_values(values)
        if block == "DCCV":
            values = normalize_dccv_values(values)
        if block == "DCNV":
            values = normalize_dcnv_values(values)
        if block == "DCLI":
            values = normalize_dcli_values(values)
        if block == "DELO":
            values = normalize_delo_values(values)
        if block == "DGER":
            values = normalize_dger_values(values)
        if block == "DBSH":
            values.pop("operation", None)
        if block == "DARE":
            area_token = values.pop("area_number", None)
        if block == "DSHL":
            values = normalize_dshl_values(values)
        if block == "DLIN":
            owner_token = values.get("owner")
            values["owner"] = None
            controlled_bus_token = values.get("controlled_bus")
            values["controlled_bus"] = None
            values = normalize_dlin_values(values)
        if block in {"DCAI", "DCER", "DCSC", "DGEI"}:
            values = map_anarede_state_to_available(values)
        if block == "DCSC":
            owner_token = values.get("owner")
            values["owner"] = None
            measurement_terminal_token = values.get("measurement_terminal")
            values["measurement_terminal"] = None

        # Derive the availability flag from the ANAREDE state token for every block.
        if "available" not in values and raw_values.get("state") is not None:
            values["available"] = str(raw_values["state"]).strip().upper() != "D"

        model = self.component_classes[block]
        record_data: dict[str, Any] = {
            "name": component_name(block, record_index, values),
            **self._to_model_values(block, values),
        }
        if block in {"DBAR", "DARE"}:
            record_data.pop("anarede_name", None)
        component = cast(AnaredeComponent, model(**record_data))
        attach_raw_component_metadata(component, line, raw_values)
        if block == "DARE" and area_token is not None:
            component.ext["area_token"] = area_token
        if block == "DLIN" and owner_token is not None:
            component.ext["owner_token"] = str(owner_token).strip().upper()
        if block == "DLIN" and controlled_bus_token is not None:
            component.ext["controlled_bus_token"] = controlled_bus_token
        if block == "DCSC" and owner_token is not None:
            component.ext["owner_token"] = str(owner_token).strip().upper()
        if block == "DCSC" and measurement_terminal_token is not None:
            component.ext["measurement_terminal_token"] = measurement_terminal_token
        return component

    def _parse_bank_record(
        self,
        line: str,
        record_index: int,
        parent_record_index: int,
        controller: Component,
    ) -> AnaredeComponent:
        values = {
            name: parse_fixed_value(slice_field(line, spec), spec)
            for name, spec in self.dbsh_bank_fields.items()
        }
        raw_values = dict(values)
        values.pop("operation", None)
        state = values.pop("state", None)
        values["parent_record_index"] = parent_record_index
        if state is not None:
            values["available"] = str(state).strip().upper() != "D"
        # A shunt bank whose controller has a To Bus is a line bank; otherwise a bus bank.
        is_line_bank = getattr(controller, "to_bus", None) is not None
        model = LineShuntBank if is_line_bank else BusShuntBank
        record_data: dict[str, Any] = {
            "name": component_name("DBSH_BANK", record_index, values),
            **self._to_model_values("DBSH_BANK", values),
        }
        component = cast(AnaredeComponent, model(**record_data))
        attach_raw_component_metadata(component, line, raw_values)
        return component

    def _derive_transformer_records_from_line(
        self,
        line_record: AnaredeComponent,
        components_by_block: dict[str, list[Component]],
    ) -> list[Component]:
        values = self._extract_dlin_values(line_record)
        records: list[Component] = []

        if has_non_default_tap(values.get("tap")) and "DLIN_TAP" in self.component_classes:
            record_index = len(components_by_block["DLIN_TAP"]) + 1
            component = self._build_dlin_derived_record(
                block="DLIN_TAP",
                values=values,
                record_index=record_index,
            )
            components_by_block["DLIN_TAP"].append(component)
            records.append(component)

        if (
            has_non_zero_angle(values.get("phase_shift"))
            and "DLIN_PHASE_SHIFT" in self.component_classes
        ):
            record_index = len(components_by_block["DLIN_PHASE_SHIFT"]) + 1
            component = self._build_dlin_derived_record(
                block="DLIN_PHASE_SHIFT",
                values=values,
                record_index=record_index,
            )
            components_by_block["DLIN_PHASE_SHIFT"].append(component)
            records.append(component)

        return records

    def _extract_dlin_values(self, line_record: AnaredeComponent) -> dict[str, ParsedScalar]:
        dlin_fields = self.mapping.get("DLIN", {}).get("fields", {})
        raw_values = line_record.ext.get("pwf_values", {})
        values: dict[str, ParsedScalar] = {}
        for field_name in dlin_fields:
            attr_name = model_field_name("DLIN", field_name)
            value = getattr(line_record, attr_name, None)
            if value is None and field_name in raw_values:
                value = raw_values[field_name]
            values[field_name] = value
        return values

    def _build_dlin_derived_record(
        self,
        block: str,
        values: dict[str, ParsedScalar],
        record_index: int,
    ) -> AnaredeComponent:
        model = self.component_classes[block]
        normalized_values = {
            key: (get_magnitude(value) if hasattr(value, "magnitude") else value)
            for key, value in values.items()
        }
        owner_token = normalized_values.get("owner")
        controlled_bus_token = normalized_values.get("controlled_bus")
        normalized_values["owner"] = None
        normalized_values["controlled_bus"] = None
        model_values = self._to_model_values(block, normalized_values)
        filtered_values = {
            field_name: value
            for field_name, value in model_values.items()
            if field_name in model.model_fields
        }
        record_data: dict[str, Any] = {
            "name": component_name(block, record_index, normalized_values),
            **filtered_values,
        }
        state_token = normalized_values.get("state")
        if state_token is not None:
            record_data["available"] = str(state_token).strip().upper() != "D"
        component = cast(AnaredeComponent, model(**record_data))
        component.ext["pwf_values"] = dict(normalized_values)
        if owner_token is not None:
            component.ext["owner_token"] = str(owner_token).strip().upper()
        if controlled_bus_token is not None:
            component.ext["controlled_bus_token"] = controlled_bus_token
        return component

    def _attach_dlin_branch_electrical_values(
        self,
        components_by_block: dict[str, list[Component]],
    ) -> None:
        for block in ("DLIN", "DLIN_TAP", "DLIN_PHASE_SHIFT"):
            for component in components_by_block.get(block, []):
                component_ext = getattr(component, "ext", None)
                if not isinstance(component_ext, dict):
                    continue
                raw_values = component_ext.get("pwf_values", {})
                if not raw_values:
                    continue

                resistance = raw_values.get("resistance")
                if resistance is not None and hasattr(component, "r"):
                    object.__setattr__(
                        component,
                        "r",
                        Percentage(float(get_magnitude(resistance)), "%"),
                    )

                reactance = raw_values.get("reactance")
                if reactance is not None and hasattr(component, "x"):
                    object.__setattr__(
                        component,
                        "x",
                        Percentage(float(get_magnitude(reactance)), "%"),
                    )

                normal_capacity = raw_values.get("normal_capacity")
                if normal_capacity is not None and hasattr(component, "rating"):
                    object.__setattr__(
                        component,
                        "rating",
                        ApparentPower(float(get_magnitude(normal_capacity)), "MVA"),
                    )

                susceptance = raw_values.get("susceptance")
                if susceptance is not None and hasattr(component, "b"):
                    b_value = ReactivePower(float(get_magnitude(susceptance)), "MVAr")
                    object.__setattr__(
                        component,
                        "b",
                        FromToToFrom(from_to=b_value, to_from=b_value),
                    )
                if susceptance is not None and hasattr(component, "g"):
                    object.__setattr__(
                        component,
                        "g",
                        FromToToFrom(
                            from_to=ActivePower(0.0, "MW"),
                            to_from=ActivePower(0.0, "MW"),
                        ),
                    )

    def _parse_pair_records(
        self,
        block: str,
        line: str,
        components_by_block: dict[str, list[Component]],
    ) -> list[Component]:
        tokens = line.split()
        if len(tokens) < 2:
            return []

        left_field, right_field = ("option", "state") if block == "DOPC" else ("mnemonic", "value")
        records: list[Component] = []
        model = self.component_classes[block]
        for i in range(0, len(tokens) - 1, 2):
            value: ParsedScalar = tokens[i + 1]
            if block == "DCTE" and looks_numeric(str(value)):
                value = parse_numeric(str(value), decimal_places=None)
            record_index = len(components_by_block[block]) + len(records) + 1
            values = {left_field: tokens[i], right_field: value}
            record_data: dict[str, Any] = {
                "name": component_name(block, record_index, values),
                **self._to_model_values(block, values),
            }
            component = model(**record_data)
            attach_raw_component_metadata(component, line, values)
            records.append(component)
        return records

    def _parse_titu_line(self, line: str) -> str:
        field_specs = self.mapping.get("TITU", {}).get("fields", {})
        title_spec = field_specs.get("title_line")
        if not title_spec:
            return line.strip()
        value = parse_fixed_value(slice_field(line, title_spec), title_spec)
        return "" if value is None else str(value).strip()

    def _section_header_name(self, stripped: str) -> str | None:
        upper = stripped.upper()
        if upper in self.mapping:
            return upper

        tokens = upper.split()
        if len(tokens) > 1 and tokens[0] == "DTPF" and tokens[1] == "CIRC":
            return "DTPF_CIRC"

        if len(tokens) > 1 and tokens[0] == "DMFL" and tokens[1] == "CIRC":
            return "DMFL_CIRC"

        if tokens and tokens[0] in self.mapping and tokens[0] in {"DOPC"}:
            return tokens[0]
        return None


def parse_anarede_system(
    pwf_path: Path | str,
    mapping_path: Path | str = MAPPING_PATH,
    system_name: str = "ANAREDE",
) -> ParsedAnaredeSystem:
    """Parse an ANAREDE `.pwf` and return a populated infrasys representation."""
    parser = AnaredeInfrasysParser(mapping_path=mapping_path, system_name=system_name)
    return parser.parse(pwf_path)


def parse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse and validate generic rows for basic package compatibility."""
    return [normalize_row(row, REQUIRED_KEYS) for row in rows]
