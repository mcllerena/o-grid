"""MATPOWER ``dcline`` table to o-grid LCC (AC/DC) record synthesis.

The ``dcline`` columns are mapped onto the ANAREDE DC records (DCBA/DCNV/
DCCV/DELO/DCLI) consumed by ``build_lcc_data``. Converter electrical
parameters that MATPOWER does not provide are taken from fixed assumptions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from o_grid.models.base import AnaredeComponent
from o_grid.models.branch import DCLine
from o_grid.models.control import ConverterControl, ConverterStation, DCLineData
from o_grid.models.enums import (
    ConverterControlSlack,
    ConverterControlType,
    ConverterMode,
    DCBusPolarity,
    DCBusType,
)
from o_grid.models.topology import DCBus
from o_grid.units import (
    ActivePower,
    Angle,
    ApparentPower,
    Percentage,
    Resistance,
    Voltage,
)

RECTIFIER_FIRING_ANGLE_DEG = 15.0
INVERTER_EXTINCTION_ANGLE_DEG = 18.0
CONVERTER_COMMUTATION_REACTANCE_PERCENT = 10.0
CONVERTER_BRIDGES = 1


def DCLines(dcline: Sequence[Mapping[str, Any]]) -> dict[str, list[AnaredeComponent]]:
    """Synthesize DCNV/DCCV/DCBA/DELO/DCLI records from MATPOWER dcline rows."""
    converters: list[AnaredeComponent] = []
    controls: list[AnaredeComponent] = []
    dc_buses: list[AnaredeComponent] = []
    links: list[AnaredeComponent] = []
    lines: list[AnaredeComponent] = []

    for link_index, row in enumerate(dcline, start=1):
        if _number(row.get("BR_STATUS", 1)) == 0:
            continue
        from_bus = _int(row.get("F_BUS"))
        to_bus = _int(row.get("T_BUS"))
        p_from = abs(_number(row.get("PF", 0.0)))
        p_to = abs(_number(row.get("PT", 0.0)))
        v_from = abs(_number(row.get("VF", 0.0)))
        v_to = abs(_number(row.get("VT", 0.0)))
        resistance = abs(_number(row.get("LOSS0", 0.0)))

        rectifier_dc_bus = 2 * link_index - 1
        inverter_dc_bus = 2 * link_index

        dc_buses.append(_build_dc_bus(rectifier_dc_bus, link_index, v_from))
        dc_buses.append(_build_dc_bus(inverter_dc_bus, link_index, v_to))

        converters.append(
            _build_converter(rectifier_dc_bus, from_bus, ConverterMode.RECTIFIER, p_from, v_from)
        )
        converters.append(
            _build_converter(inverter_dc_bus, to_bus, ConverterMode.INVERTER, p_to, v_to)
        )

        controls.append(
            _build_control(
                rectifier_dc_bus,
                ConverterControlSlack.NORMAL,
                ConverterControlType.POWER,
                p_from,
                RECTIFIER_FIRING_ANGLE_DEG,
            )
        )
        controls.append(
            _build_control(
                inverter_dc_bus,
                ConverterControlSlack.SLACK,
                ConverterControlType.CURRENT,
                0.0,
                INVERTER_EXTINCTION_ANGLE_DEG,
            )
        )

        link = DCLineData(
            name=f"DC Link {link_index}",
            number=link_index,
            voltage=Voltage(v_from, "kV"),
            power_base=ActivePower(p_from, "MW"),
        )
        link.ext["pwf_values"] = {
            "number": link_index,
            "name": f"DC Link {link_index}",
            "voltage": v_from,
            "power_base": p_from,
        }
        links.append(link)

        line = DCLine(
            name=f"dc_{from_bus}_{to_bus}",
            from_bus=rectifier_dc_bus,
            to_bus=inverter_dc_bus,
            dcli_circuit=1,
            resistance=Resistance(resistance, "ohm"),
            capacity=ActivePower(max(p_from, p_to), "MW"),
        )
        line.ext["pwf_values"] = {
            "from_bus": rectifier_dc_bus,
            "to_bus": inverter_dc_bus,
            "resistance": resistance,
        }
        lines.append(line)

    return {
        "DCBA": dc_buses,
        "DCNV": converters,
        "DCCV": controls,
        "DELO": links,
        "DCLI": lines,
    }


def _build_dc_bus(number: int, link_index: int, voltage_kv: float) -> DCBus:
    component = DCBus(
        name=f"DC Bus {number}",
        number=number,
        polarity=DCBusPolarity.POSITIVE_POLE,
        type=DCBusType.REFERENCE,
        voltage=Voltage(voltage_kv, "kV"),
        dc_link_number=link_index,
    )
    component.ext["pwf_values"] = {
        "number": number,
        "voltage": voltage_kv,
        "dc_link_number": link_index,
    }
    return component


def _build_converter(
    dc_bus: int,
    ac_bus: int,
    mode: ConverterMode,
    power_mva: float,
    voltage_kv: float,
) -> ConverterStation:
    component = ConverterStation(
        name=f"Converter {dc_bus}",
        number=dc_bus,
        ac_bus=ac_bus,
        dc_bus=dc_bus,
        mode=mode,
        six_pulse_bridges=CONVERTER_BRIDGES,
        transformer_power=ApparentPower(power_mva, "MVA"),
        secondary_voltage=Voltage(voltage_kv, "kV"),
        commutation_reactance=Percentage(CONVERTER_COMMUTATION_REACTANCE_PERCENT, "%"),
    )
    component.ext["pwf_values"] = {
        "number": dc_bus,
        "dc_bus": dc_bus,
        "ac_bus": ac_bus,
        "mode": mode.value,
        "commutation_reactance": CONVERTER_COMMUTATION_REACTANCE_PERCENT,
        "secondary_voltage": voltage_kv,
        "transformer_power": power_mva,
        "six_pulse_bridges": CONVERTER_BRIDGES,
    }
    return component


def _build_control(
    number: int,
    slack: ConverterControlSlack,
    control_type: ConverterControlType,
    specified_value: float,
    angle_deg: float,
) -> ConverterControl:
    component = ConverterControl(
        name=f"Converter Control {number}",
        number=number,
        slack=slack,
        converter_control_type=control_type,
        specified_value=specified_value,
        converter_angle=Angle(angle_deg, "degree"),
        tap_reduced_voltage_mode=1.0,
        minimum_transformer_tap=0.0,
        maximum_transformer_tap=0.0,
    )
    component.ext["pwf_values"] = {
        "number": number,
        "slack": slack.value,
        "converter_control_type": control_type.value,
        "specified_value": specified_value,
        "converter_angle": angle_deg,
        "tap_reduced_voltage_mode": 1.0,
        "minimum_transformer_tap": 0.0,
        "maximum_transformer_tap": 0.0,
    }
    return component


def _int(value: Any) -> int:
    return int(float(value))


def _number(value: Any) -> float:
    return float(value)
