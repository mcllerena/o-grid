"""Pydantic models for ANAREDE NTW records."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from o_grid.models import topology as topology_models
from o_grid.models.base import AnaredeComponent
from o_grid.models.branch import ACLine as BaseACLine
from o_grid.models.branch import TransformerDevice as BaseTransformer
from o_grid.models.generators import Generator as BaseGenerator
from o_grid.models.load import IndividualizedLoad as BaseLoad
from o_grid.models.topology import ACBus as BaseACBus
from o_grid.models.topology import Area as BaseArea
from o_grid.models.topology import Topology
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Current,
    Distance,
    Percentage,
    PerUnit,
    ReactivePower,
    Resistance,
    Voltage,
)


class Area(BaseArea):
    """NTW area record: area number, switch, interchange and name."""

    name: Annotated[str, Field(description="Canonical area component name.")] = ""
    area_switch_id: Annotated[int | None, Field(description="Area switch identifier.")] = None
    interchange_active_power: Annotated[
        ActivePower,
        Field(description="Internal area interchange in MW.", json_schema_extra={"units": "MW"}),
    ] = ActivePower(0.0, "MW")
    area_name: Annotated[str, Field(description="Area name from the NTW record.")] = ""


class Zone(Topology):
    """NTW zone record containing the zone identifier and display name."""

    name: Annotated[str, Field(description="Canonical zone component name.")] = ""
    zone_number: Annotated[int | None, Field(description="Zone identifier.")] = None
    zone_name: Annotated[str, Field(description="Zone name from the NTW record.")] = ""


class Substation(Topology):
    """NTW substation record containing identifier, name and geographic coordinates."""

    name: Annotated[str, Field(description="Canonical substation component name.")] = ""
    substation_number: Annotated[int | None, Field(description="Substation identifier.")] = None
    substation_name: Annotated[str, Field(description="Substation name.")] = ""
    latitude: Annotated[float | None, Field(description="Substation latitude in degrees.")] = None
    longitude: Annotated[float | None, Field(description="Substation longitude in degrees.")] = None


class Owner(Topology):
    """NTW owner record containing the owner identifier and name."""

    name: Annotated[str, Field(description="Canonical owner component name.")] = ""
    owner_number: Annotated[int | None, Field(description="Owner identifier.")] = None
    owner_name: Annotated[str, Field(description="Owner name.")] = ""


class ACBus(BaseACBus):
    """NTW BUS DATA record.

    In addition to the shared bus operating-point fields, NTW stores shunt status,
    ZIP-independent voltage thresholds, ownership, substation and bus-scheme data.
    Bus type values are 0=load, 1=load with voltage limits, 2=generation,
    3=swing and 4=de-energized.
    """

    name: Annotated[str, Field(description="Canonical bus component name.")] = ""
    bus_id: Annotated[
        int | float | str | None, Field(description="Bus identification nnnnnn.ii.")
    ] = None
    bus_name: Annotated[str, Field(description="Bus name, up to 12 characters.")] = ""
    shunt_status: Annotated[int | None, Field(description="Bus shunt status: 0=off, 1=on.")] = None
    shunt_conductance: Annotated[
        ActivePower, Field(description="Bus shunt conductance Gsht in MW.")
    ] = ActivePower(0.0, "MW")
    shunt_susceptance: Annotated[
        ReactivePower, Field(description="Bus shunt susceptance Bsht in MVAr.")
    ] = ReactivePower(0.0, "MVAr")
    zone_number: Annotated[int | None, Field(description="Number of the bus zone.")] = None
    voltage_magnitude: Annotated[PerUnit, Field(description="Bus voltage magnitude in p.u.")] = (
        PerUnit(1.0, "pu")
    )
    voltage_angle: Annotated[Angle, Field(description="Bus voltage angle in degrees.")] = Angle(
        0.0, "degree"
    )
    overvoltage_threshold: Annotated[
        PerUnit | None, Field(description="Overvoltage detection threshold in p.u.")
    ] = None
    undervoltage_threshold: Annotated[
        PerUnit | None, Field(description="Undervoltage detection threshold in p.u.")
    ] = None
    emergency_overvoltage_threshold: Annotated[
        PerUnit | None, Field(description="Emergency overvoltage threshold in p.u.")
    ] = None
    emergency_undervoltage_threshold: Annotated[
        PerUnit | None, Field(description="Emergency undervoltage threshold in p.u.")
    ] = None
    owner_number: Annotated[int | None, Field(description="Bus owner number.")] = None
    substation_number: Annotated[int | None, Field(description="Bus substation number.")] = None
    bus_scheme: Annotated[
        int | None,
        Field(
            description="Bus scheme: 0=undefined, 1=single, 2=main/auxiliary, 3/4=double bus, 5=ring, 6=breaker-and-half."  # noqa: E501
        ),
    ] = None


class Load(BaseLoad):
    """NTW LOAD DATA record using the ZIP load decomposition.

    Constant-power, constant-current and constant-impedance active/reactive
    values are stored separately, followed by owner, zero-sequence impedance
    and the load name. Status values are 0=off and 1=on.
    """

    name: Annotated[str, Field(description="Canonical load component name.")] = ""
    bus_id: Annotated[
        int | float | str | None, Field(description="Load bus identification nnnnnn.ii.")
    ] = None
    load_identifier: Annotated[str, Field(description="Load identifier, up to 2 characters.")] = ""
    status: Annotated[int | None, Field(description="Load status: 0=off, 1=on.")] = None
    constant_power_active: Annotated[
        ActivePower, Field(description="Constant-power active load in MW.")
    ] = ActivePower(0.0, "MW")
    constant_power_reactive: Annotated[
        ReactivePower, Field(description="Constant-power reactive load in MVAr.")
    ] = ReactivePower(0.0, "MVAr")
    constant_current_active: Annotated[
        ActivePower, Field(description="Constant-current active load in MW.")
    ] = ActivePower(0.0, "MW")
    constant_current_reactive: Annotated[
        ReactivePower, Field(description="Constant-current reactive load in MVAr.")
    ] = ReactivePower(0.0, "MVAr")
    constant_impedance_active: Annotated[
        ActivePower, Field(description="Constant-impedance active load in MW.")
    ] = ActivePower(0.0, "MW")
    constant_impedance_reactive: Annotated[
        ReactivePower, Field(description="Constant-impedance reactive load in MVAr.")
    ] = ReactivePower(0.0, "MVAr")
    owner_number: Annotated[int | None, Field(description="Load owner number.")] = None
    zero_sequence_resistance: Annotated[
        PerUnit | None, Field(description="Load zero-sequence resistance in p.u.")
    ] = None
    zero_sequence_reactance: Annotated[
        PerUnit | None, Field(description="Load zero-sequence reactance in p.u.")
    ] = None
    load_name: Annotated[str, Field(description="Load name.")] = ""


class Generator(BaseGenerator):
    """NTW GENERATOR DATA record using Version 6 columns.

    The model covers dispatch, reactive limits, voltage control, step-up
    transformer data, participation, sequence impedances, capability data and
    generator technology. For NTW versions greater than 7, the Version 6
    column layout is used as documented by ANAREDE.
    """

    name: Annotated[str, Field(description="Canonical generator component name.")] = ""
    bus_id: Annotated[
        int | float | str | None, Field(description="Generator bus identification nnnnnn.ii.")
    ] = None
    generator_identifier: Annotated[
        str, Field(description="Generator identifier, up to 2 characters.")
    ] = ""
    reactive_generation: Annotated[
        ReactivePower | None, Field(description="Generator reactive output in MVAr.")
    ] = None
    maximum_reactive_generation: Annotated[
        ReactivePower | None, Field(description="Maximum reactive generation in MVAr.")
    ] = None
    minimum_reactive_generation: Annotated[
        ReactivePower | None, Field(description="Minimum reactive generation in MVAr.")
    ] = None
    specified_voltage: Annotated[
        PerUnit | None, Field(description="Specified controlled voltage in p.u.")
    ] = None
    controlled_bus_id: Annotated[
        int | float | str | None, Field(description="Controlled bus identification nnnnnn.ii.")
    ] = None
    power_base: Annotated[
        ApparentPower | None, Field(description="Generator power base in MVA.")
    ] = None
    transformer_resistance: Annotated[
        PerUnit | None, Field(description="Step-up transformer resistance in p.u.")
    ] = None
    transformer_reactance: Annotated[
        PerUnit | None, Field(description="Step-up transformer reactance in p.u.")
    ] = None
    transformer_tap: Annotated[
        PerUnit | None, Field(description="Step-up transformer tap in p.u.")
    ] = None
    status: Annotated[int | None, Field(description="Generator status: 0=off, 1=on.")] = None
    remote_control_participation: Annotated[
        Percentage | None, Field(description="Remote voltage-control participation in percent.")
    ] = None
    maximum_active_generation: Annotated[
        ActivePower | None, Field(description="Maximum active generation in MW.")
    ] = None
    minimum_active_generation: Annotated[
        ActivePower | None, Field(description="Minimum active generation in MW.")
    ] = None
    group_number: Annotated[int | None, Field(description="Generator group number.")] = None
    unavailable: Annotated[
        int | None, Field(description="Generator availability: 0=available, 1=unavailable.")
    ] = None
    owner_number: Annotated[int | None, Field(description="Generator owner number.")] = None
    ground_connection: Annotated[
        int | None, Field(description="Ground connection: 1=grounded star, 2=star, 3=delta.")
    ] = None
    positive_sequence_resistance: Annotated[
        PerUnit | None,
        Field(
            description="Positive-sequence resistance or converter short-circuit current in p.u."
        ),
    ] = None
    positive_sequence_reactance: Annotated[
        PerUnit | None,
        Field(description="Positive-sequence reactance or converter power factor in p.u."),
    ] = None
    negative_sequence_resistance: Annotated[
        PerUnit | None, Field(description="Negative-sequence resistance in p.u.")
    ] = None
    negative_sequence_reactance: Annotated[
        PerUnit | None, Field(description="Negative-sequence reactance in p.u.")
    ] = None
    zero_sequence_resistance: Annotated[
        PerUnit | None, Field(description="Zero-sequence resistance in p.u.")
    ] = None
    zero_sequence_reactance: Annotated[
        PerUnit | None, Field(description="Zero-sequence reactance in p.u.")
    ] = None
    grounding_resistance: Annotated[
        PerUnit | None, Field(description="Grounding resistance in p.u.")
    ] = None
    grounding_reactance: Annotated[
        PerUnit | None, Field(description="Grounding reactance in p.u.")
    ] = None
    quadrature_reactance: Annotated[
        PerUnit | None,
        Field(description="Quadrature reactance used for capability computation in p.u."),
    ] = None
    stator_current_service_factor: Annotated[
        float | None, Field(description="Stator current service factor, normally 1.0 to 1.4.")
    ] = None
    maximum_loading_angle: Annotated[
        Angle | None, Field(description="Maximum loading angle, normally 60 to 85 degrees.")
    ] = None
    generator_type: Annotated[
        int | None, Field(description="Generator type: 0=hydro, 1=steam, 2=gas, 3-6=wind, 7=PV.")
    ] = None
    generator_unit_name: Annotated[
        str, Field(description="Generator unit name, up to 20 characters.")
    ] = ""


class TransmissionLine(BaseACLine):
    """NTW TRANSMISSION LINE DATA record using Version 6 columns.

    It contains terminal identifiers, series parameters, three thermal limits,
    breaker statuses, length, area/owner, zero-sequence data, branch name and
    three pairs of terminal line-shunt controls.
    """

    name: Annotated[str, Field(description="Canonical transmission-line component name.")] = ""
    from_bus_id: Annotated[
        int | float | str | None, Field(description="From-bus identification nnnnnn.ii.")
    ] = None
    to_bus_id: Annotated[
        int | float | str | None, Field(description="To-bus identification nnnnnn.ii.")
    ] = None
    circuit_identifier: Annotated[str, Field(description="Parallel circuit identifier.")] = ""
    series_resistance: Annotated[PerUnit | None, Field(description="Series resistance in p.u.")] = (
        None
    )
    series_reactance: Annotated[PerUnit | None, Field(description="Series reactance in p.u.")] = (
        None
    )
    line_charging: Annotated[
        ReactivePower | None, Field(description="Total line charging in MVAr.")
    ] = None
    limit_1: Annotated[ApparentPower | None, Field(description="Normal line limit 1 in MVA.")] = (
        None
    )
    limit_2: Annotated[ApparentPower | None, Field(description="Line limit 2 in MVA.")] = None
    limit_3: Annotated[ApparentPower | None, Field(description="Line limit 3 in MVA.")] = None
    from_breaker_status: Annotated[
        int | None, Field(description="From-terminal breaker: 0=off, 1=on, 2=maintenance.")
    ] = None
    to_breaker_status: Annotated[
        int | None, Field(description="To-terminal breaker: 0=off, 1=on, 2=maintenance.")
    ] = None
    line_length: Annotated[Distance | None, Field(description="Line length in km.")] = None
    area_number: Annotated[int | None, Field(description="Line area number.")] = None
    owner_number: Annotated[int | None, Field(description="Line owner number.")] = None
    zero_sequence_resistance: Annotated[
        PerUnit | None, Field(description="Zero-sequence resistance in p.u.")
    ] = None
    zero_sequence_reactance: Annotated[
        PerUnit | None, Field(description="Zero-sequence reactance in p.u.")
    ] = None
    zero_sequence_charging: Annotated[
        PerUnit | None, Field(description="Zero-sequence charging in p.u.")
    ] = None
    branch_name: Annotated[str, Field(description="Branch name, up to 23 characters.")] = ""
    controlled_from_bus_id: Annotated[
        int | float | str | None,
        Field(description="Bus controlled by the from-terminal line shunt."),
    ] = None
    from_shunt_control_status: Annotated[
        int | None, Field(description="From-terminal line-shunt control status: 0=off, 1=on.")
    ] = None
    controlled_to_bus_id: Annotated[
        int | float | str | None, Field(description="Bus controlled by the to-terminal line shunt.")
    ] = None
    to_shunt_control_status: Annotated[
        int | None, Field(description="To-terminal line-shunt control status: 0=off, 1=on.")
    ] = None
    from_shunt_1_status: Annotated[
        int | None, Field(description="From-terminal shunt 1 status: 0=off, 1=on.")
    ] = None
    from_shunt_1_conductance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 1 conductance in p.u.")
    ] = None
    from_shunt_1_susceptance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 1 susceptance in p.u.")
    ] = None
    to_shunt_1_status: Annotated[
        int | None, Field(description="To-terminal shunt 1 status: 0=off, 1=on.")
    ] = None
    to_shunt_1_conductance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 1 conductance in p.u.")
    ] = None
    to_shunt_1_susceptance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 1 susceptance in p.u.")
    ] = None
    from_shunt_2_status: Annotated[
        int | None, Field(description="From-terminal shunt 2 status: 0=off, 1=on.")
    ] = None
    from_shunt_2_conductance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 2 conductance in p.u.")
    ] = None
    from_shunt_2_susceptance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 2 susceptance in p.u.")
    ] = None
    to_shunt_2_status: Annotated[
        int | None, Field(description="To-terminal shunt 2 status: 0=off, 1=on.")
    ] = None
    to_shunt_2_conductance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 2 conductance in p.u.")
    ] = None
    to_shunt_2_susceptance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 2 susceptance in p.u.")
    ] = None
    from_shunt_3_status: Annotated[
        int | None, Field(description="From-terminal shunt 3 status: 0=off, 1=on.")
    ] = None
    from_shunt_3_conductance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 3 conductance in p.u.")
    ] = None
    from_shunt_3_susceptance: Annotated[
        PerUnit | None, Field(description="From-terminal shunt 3 susceptance in p.u.")
    ] = None
    to_shunt_3_status: Annotated[
        int | None, Field(description="To-terminal shunt 3 status: 0=off, 1=on.")
    ] = None
    to_shunt_3_conductance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 3 conductance in p.u.")
    ] = None
    to_shunt_3_susceptance: Annotated[
        PerUnit | None, Field(description="To-terminal shunt 3 susceptance in p.u.")
    ] = None


class Transformer(BaseTransformer):
    """First record of a Version 6 NTW TRANSFORMER DATA entry.

    Version 6 represents each transformer with an identification record and
    one continuation record for a two-winding transformer, or three
    continuation records for a three-winding transformer. This class models
    the identification record: buses, circuit, magnetizing values, winding
    statuses and star-point voltage.
    """

    name: Annotated[str, Field(description="Canonical transformer component name.")] = ""
    from_bus_id: Annotated[
        int | float | str | None,
        Field(description="First transformer bus identification nnnnnn.ii."),
    ] = None
    to_bus_id: Annotated[
        int | float | str | None,
        Field(description="Second transformer bus identification nnnnnn.ii."),
    ] = None
    third_bus_id: Annotated[
        int | float | str | None,
        Field(
            description="Third transformer bus identification, or zero for two-winding transformers."  # noqa: E501
        ),
    ] = None
    circuit_identifier: Annotated[str, Field(description="Transformer circuit identifier.")] = ""
    magnetizing_conductance: Annotated[
        PerUnit | None, Field(description="Magnetizing conductance in p.u. on the system base.")
    ] = None
    magnetizing_susceptance: Annotated[
        PerUnit | None, Field(description="Magnetizing susceptance in p.u. on the system base.")
    ] = None
    winding_1_status: Annotated[int | None, Field(description="Winding 1 status: 0=off, 1=on.")] = (
        None
    )
    winding_2_status: Annotated[int | None, Field(description="Winding 2 status: 0=off, 1=on.")] = (
        None
    )
    winding_3_status: Annotated[int | None, Field(description="Winding 3 status: 0=off, 1=on.")] = (
        None
    )
    star_point_voltage: Annotated[
        PerUnit | None, Field(description="Three-winding transformer star-point voltage in p.u.")
    ] = None
    branch_name: Annotated[str, Field(description="Transformer branch name.")] = ""


class ShuntDevice(AnaredeComponent):
    """NTW SHUNT DATA record with up to eight switched elements."""

    bus_id: Annotated[
        int | float | str | None, Field(description="Bus identification nnnnnn.ii.")
    ] = None
    control_mode: Annotated[
        int | None, Field(description="Control mode: 0=fixed, 1=discrete, 2=continuous or SVC.")
    ] = None
    voltage_maximum: Annotated[
        PerUnit | None,
        Field(description="Upper voltage control bound or specified voltage in p.u."),
    ] = None
    voltage_minimum: Annotated[
        PerUnit | None, Field(description="Lower voltage control bound in p.u.")
    ] = None
    controlled_bus_id: Annotated[
        int | float | str | None, Field(description="Controlled bus identification nnnnnn.ii.")
    ] = None
    initial_admittance: Annotated[
        ReactivePower | None, Field(description="Initial shunt admittance at 1 p.u. in MVAr.")
    ] = None
    status: Annotated[int | None, Field(description="Global shunt status: 0=off, 1=on.")] = None
    element_1_status: Annotated[
        int | None, Field(description="Element 1 availability: 0=maintenance, 1=available.")
    ] = None
    element_1_count: Annotated[int | None, Field(description="Number of elements in stage 1.")] = (
        None
    )
    element_1_size: Annotated[
        ReactivePower | None, Field(description="Element 1 size in MVAr.")
    ] = None
    element_1_zero_sequence_impedance: Annotated[
        PerUnit | None, Field(description="Element 1 zero-sequence impedance in p.u.")
    ] = None
    element_2_status: Annotated[
        int | None, Field(description="Element 2 availability: 0=maintenance, 1=available.")
    ] = None
    element_2_count: Annotated[int | None, Field(description="Number of elements in stage 2.")] = (
        None
    )
    element_2_size: Annotated[
        ReactivePower | None, Field(description="Element 2 size in MVAr.")
    ] = None
    element_2_zero_sequence_impedance: Annotated[
        PerUnit | None, Field(description="Element 2 zero-sequence impedance in p.u.")
    ] = None
    element_3_status: Annotated[
        int | None, Field(description="Element 3 availability: 0=maintenance, 1=available.")
    ] = None
    element_3_count: Annotated[int | None, Field(description="Number of elements in stage 3.")] = (
        None
    )
    element_3_size: Annotated[
        ReactivePower | None, Field(description="Element 3 size in MVAr.")
    ] = None
    element_3_zero_sequence_impedance: Annotated[
        PerUnit | None, Field(description="Element 3 zero-sequence impedance in p.u.")
    ] = None


class SeriesCapacitor(BaseACLine):
    """NTW SERIES CAPACITOR DATA record."""

    from_bus_id: Annotated[
        int | float | str | None, Field(description="From-bus identification nnnnnn.ii.")
    ] = None
    to_bus_id: Annotated[
        int | float | str | None, Field(description="To-bus identification nnnnnn.ii.")
    ] = None
    circuit_identifier: Annotated[
        str, Field(description="Series capacitor circuit identifier.")
    ] = ""
    series_resistance: Annotated[PerUnit | None, Field(description="Series resistance in p.u.")] = (
        None
    )
    series_reactance: Annotated[PerUnit | None, Field(description="Series reactance in p.u.")] = (
        None
    )
    limit_1: Annotated[ApparentPower | None, Field(description="Limit 1 in MVA.")] = None
    limit_2: Annotated[ApparentPower | None, Field(description="Limit 2 in MVA.")] = None
    limit_3: Annotated[ApparentPower | None, Field(description="Limit 3 in MVA.")] = None
    from_shunt_status: Annotated[
        int | None, Field(description="From-bus shunt status: 0=off, 1=on.")
    ] = None
    from_shunt_conductance: Annotated[
        PerUnit | None, Field(description="From-bus shunt conductance in p.u.")
    ] = None
    from_shunt_susceptance: Annotated[
        PerUnit | None, Field(description="From-bus shunt susceptance in p.u.")
    ] = None
    to_shunt_status: Annotated[
        int | None, Field(description="To-bus shunt status: 0=off, 1=on.")
    ] = None
    to_shunt_conductance: Annotated[
        PerUnit | None, Field(description="To-bus shunt conductance in p.u.")
    ] = None
    to_shunt_susceptance: Annotated[
        PerUnit | None, Field(description="To-bus shunt susceptance in p.u.")
    ] = None
    from_breaker_status: Annotated[
        int | None, Field(description="From-bus breaker status: 0=off, 1=on, 2=maintenance.")
    ] = None
    to_breaker_status: Annotated[
        int | None, Field(description="To-bus breaker status: 0=off, 1=on, 2=maintenance.")
    ] = None
    owner_number: Annotated[int | None, Field(description="Series capacitor owner number.")] = None
    branch_name: Annotated[str, Field(description="Series capacitor branch name.")] = ""


class DCLink(AnaredeComponent):
    """NTW HVDC control record from DC LINK DATA."""

    pole_id: Annotated[int | float | str | None, Field(description="DC pole identifier.")] = None
    area_number: Annotated[int | None, Field(description="DC pole area number.")] = None
    zone_number: Annotated[int | None, Field(description="DC pole zone number.")] = None
    control_mode: Annotated[
        int | None,
        Field(
            description=(
                "Control mode: 1=power inverter, 2=current inverter, 3=power rectifier, "
                "4=current rectifier."
            )
        ),
    ] = None
    line_resistance: Annotated[
        Resistance | None, Field(description="DC line resistance in ohms.")
    ] = None
    control_set_value: Annotated[
        ActivePower | Current | None, Field(description="DC control set value in MW or A.")
    ] = None
    scheduled_voltage: Annotated[
        Voltage | None, Field(description="Scheduled DC voltage in kV.")
    ] = None
    current_threshold_voltage: Annotated[
        Voltage | None,
        Field(description="Voltage threshold for power-to-current control conversion in kV."),
    ] = None
    current_margin: Annotated[
        PerUnit | None, Field(description="Current margin for inverter control in p.u.")
    ] = None
    status: Annotated[int | None, Field(description="DC pole status: 0=off, 1=on.")] = None
    nominal_voltage: Annotated[Voltage | None, Field(description="Nominal DC voltage in kV.")] = (
        None
    )
    nominal_power: Annotated[ActivePower | None, Field(description="Nominal DC power in MW.")] = (
        None
    )
    pole_name: Annotated[str, Field(description="DC pole name, up to 23 characters.")] = ""


class ImpedanceCorrection(AnaredeComponent):
    """Transformer impedance correction table record."""

    table_number: Annotated[
        int | None, Field(description="Transformer correction table number.")
    ] = None
    tap_1: Annotated[float | None, Field(description="First tap or phase-shift value.")] = None
    correction_1: Annotated[float | None, Field(description="First correction factor.")] = None
    tap_2: Annotated[float | None, Field(description="Second tap or phase-shift value.")] = None
    correction_2: Annotated[float | None, Field(description="Second correction factor.")] = None
    tap_3: Annotated[float | None, Field(description="Third tap or phase-shift value.")] = None
    correction_3: Annotated[float | None, Field(description="Third correction factor.")] = None


class LineMutualImpedance(AnaredeComponent):
    """Mutual impedance between two transmission-line sections."""

    line_1_from_bus: Annotated[
        int | float | str | None, Field(description="From bus of line 1.")
    ] = None
    line_1_to_bus: Annotated[int | float | str | None, Field(description="To bus of line 1.")] = (
        None
    )
    line_1_circuit: Annotated[str, Field(description="Circuit identifier of line 1.")] = ""
    line_1_start_percent: Annotated[
        Percentage | None, Field(description="Mutual section start distance on line 1 in percent.")
    ] = None
    line_1_end_percent: Annotated[
        Percentage | None, Field(description="Mutual section end distance on line 1 in percent.")
    ] = None
    line_2_from_bus: Annotated[
        int | float | str | None, Field(description="From bus of line 2.")
    ] = None
    line_2_to_bus: Annotated[int | float | str | None, Field(description="To bus of line 2.")] = (
        None
    )
    line_2_circuit: Annotated[str, Field(description="Circuit identifier of line 2.")] = ""
    line_2_start_percent: Annotated[
        Percentage | None, Field(description="Mutual section start distance on line 2 in percent.")
    ] = None
    line_2_end_percent: Annotated[
        Percentage | None, Field(description="Mutual section end distance on line 2 in percent.")
    ] = None
    mutual_resistance: Annotated[PerUnit | None, Field(description="Mutual resistance in p.u.")] = (
        None
    )
    mutual_reactance: Annotated[PerUnit | None, Field(description="Mutual reactance in p.u.")] = (
        None
    )


class InductionMotor(AnaredeComponent):
    """NTW induction motor record."""

    bus_id: Annotated[int | float | str | None, Field(description="Motor bus identification.")] = (
        None
    )
    motor_identifier: Annotated[str, Field(description="Motor identifier.")] = ""
    status: Annotated[int | None, Field(description="Motor status: 0=off, 1=on.")] = None
    unit_count: Annotated[int | None, Field(description="Number of motor units.")] = None
    unit_apparent_power: Annotated[
        ApparentPower | None, Field(description="Apparent power of one motor unit in MVA.")
    ] = None
    active_power: Annotated[
        ActivePower | None,
        Field(description="Active power consumption in MW; negative indicates generation."),
    ] = None
    reactive_power: Annotated[
        ReactivePower | None,
        Field(description="Reactive power consumption in MVAr; positive is inductive."),
    ] = None
    stator_resistance: Annotated[
        PerUnit | None, Field(description="Stator resistance in machine p.u.")
    ] = None
    stator_reactance: Annotated[
        PerUnit | None, Field(description="Stator reactance in machine p.u.")
    ] = None
    magnetizing_reactance: Annotated[
        PerUnit | None, Field(description="Magnetizing reactance in machine p.u.")
    ] = None
    rotor_1_resistance: Annotated[
        PerUnit | None, Field(description="Rotor cage 1 resistance in machine p.u.")
    ] = None
    rotor_1_reactance: Annotated[
        PerUnit | None, Field(description="Rotor cage 1 reactance in machine p.u.")
    ] = None
    rotor_2_resistance: Annotated[
        PerUnit | None, Field(description="Rotor cage 2 resistance in machine p.u.")
    ] = None
    rotor_2_reactance: Annotated[
        PerUnit | None, Field(description="Rotor cage 2 reactance in machine p.u.")
    ] = None
    saturation_1_pu: Annotated[PerUnit | None, Field(description="Saturation at 1.0 p.u.")] = None
    saturation_1_2_pu: Annotated[PerUnit | None, Field(description="Saturation at 1.2 p.u.")] = None
    grounding: Annotated[
        str | None, Field(description="Grounded-star marker G, or 0 otherwise.")
    ] = None
    standard: Annotated[
        str | None, Field(description="Motor standard: 0=custom, A-E=NEMA, N/H=IEC.")
    ] = None
    owner_number: Annotated[int | None, Field(description="Motor owner number.")] = None
    motor_name: Annotated[str, Field(description="Motor name, up to 12 characters.")] = ""


class BreakerConfiguration(AnaredeComponent):
    """NTW breaker configuration record."""

    bus_number: Annotated[int | None, Field(description="Bus number.")] = None
    node_1: Annotated[str | None, Field(description="First series-connected breaker node ID.")] = (
        None
    )
    node_2: Annotated[str | None, Field(description="Second series-connected breaker node ID.")] = (
        None
    )
    node_3: Annotated[str | None, Field(description="Third series-connected breaker node ID.")] = (
        None
    )
    node_4: Annotated[str | None, Field(description="Fourth series-connected breaker node ID.")] = (
        None
    )


class FACTSDevice(AnaredeComponent):
    """NTW FACTS device record."""

    device_name: Annotated[str, Field(description="FACTS device name.")] = ""
    send_bus_id: Annotated[
        int | float | str | None, Field(description="Sending bus identification.")
    ] = None
    terminal_bus_id: Annotated[
        int | float | str | None, Field(description="Terminal bus identification.")
    ] = None
    circuit_identifier: Annotated[str, Field(description="FACTS circuit identifier.")] = ""
    device_type: Annotated[int | None, Field(description="FACTS type number.")] = None
    active_reference: Annotated[
        ActivePower | None, Field(description="Active-power reference Pref in MW.")
    ] = None
    reactive_reference: Annotated[
        ReactivePower | None, Field(description="Reactive-power reference Qref in MVAr.")
    ] = None
    voltage_reference: Annotated[
        PerUnit | None, Field(description="Voltage reference Vref in p.u.")
    ] = None
    maximum_shunt_current: Annotated[
        ApparentPower | None, Field(description="Maximum shunt current Ishtmax in MVA.")
    ] = None
    maximum_power_transfer: Annotated[
        ActivePower | None, Field(description="Maximum shunt/series power transfer Ptrmax in MW.")
    ] = None
    terminal_voltage_minimum: Annotated[
        PerUnit | None, Field(description="Minimum terminal voltage or Xc minimum in p.u.")
    ] = None
    terminal_voltage_maximum: Annotated[
        PerUnit | None, Field(description="Maximum terminal voltage or Xc maximum in p.u.")
    ] = None
    series_voltage_maximum: Annotated[
        PerUnit | None, Field(description="Maximum series converter voltage in p.u.")
    ] = None
    series_voltage_minimum: Annotated[
        PerUnit | None, Field(description="Minimum series converter voltage in p.u.")
    ] = None
    series_current_maximum: Annotated[
        PerUnit | None, Field(description="Maximum series current in p.u.")
    ] = None
    series_current_emergency: Annotated[
        PerUnit | None, Field(description="Emergency series current in p.u.")
    ] = None
    series_current_minimum: Annotated[
        PerUnit | None, Field(description="Minimum series current in p.u.")
    ] = None
    series_reactance: Annotated[
        PerUnit | None, Field(description="Series reactance Xc in p.u.")
    ] = None
    droop: Annotated[PerUnit | None, Field(description="Voltage/current droop ratio in p.u.")] = (
        None
    )
    status: Annotated[int | None, Field(description="FACTS status: 0=off, 1=on.")] = None
    owner_number: Annotated[int | None, Field(description="FACTS owner number.")] = None


ACBus.model_rebuild(_types_namespace=vars(topology_models))
for _model in (
    ShuntDevice,
    SeriesCapacitor,
    DCLink,
    ImpedanceCorrection,
    LineMutualImpedance,
    InductionMotor,
    BreakerConfiguration,
    FACTSDevice,
    Owner,
):
    _model.model_rebuild(_types_namespace={**vars(topology_models), **globals()})


__all__ = [
    "ACBus",
    "Area",
    "BreakerConfiguration",
    "DCLink",
    "FACTSDevice",
    "Generator",
    "ImpedanceCorrection",
    "InductionMotor",
    "LineMutualImpedance",
    "Load",
    "Owner",
    "SeriesCapacitor",
    "ShuntDevice",
    "Substation",
    "Transformer",
    "TransmissionLine",
    "Zone",
]
