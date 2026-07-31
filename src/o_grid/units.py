"""o_grid pint units."""

from __future__ import annotations

from infrasys.base_quantity import BaseQuantity, ureg
from pint import Quantity

ureg.formatter.default_format = "~"


def _define_unit(definition: str, unit_name: str) -> None:
    units = getattr(ureg, "_units", {})
    if unit_name not in units:
        ureg.define(definition)


_define_unit("VAr = volt_ampere = volt_ampere_reactive", "VAr")
_define_unit(
    "MVAr = 1e6 * VAr = megavolt_ampere_reactive",
    "MVAr",
)
_define_unit("pu = [] = per_unit", "pu")


class Distance(BaseQuantity):
    __base_unit__ = "meter"


class Voltage(BaseQuantity):
    __base_unit__ = "kilovolt"

    def __repr__(self) -> str:
        return f"<Quantity({self.magnitude!r}, 'kV')>"


class Current(BaseQuantity):
    __base_unit__ = "ampere"


class Angle(BaseQuantity):
    __base_unit__ = "degree"


class ActivePower(BaseQuantity):
    __base_unit__ = "megawatt"

    def __repr__(self) -> str:
        return f"<Quantity({self.magnitude!r}, 'MW')>"


class ApparentPower(BaseQuantity):
    __base_unit__ = "MVA"


class ReactivePower(BaseQuantity):
    __base_unit__ = "MVAr"


class Time(BaseQuantity):
    __base_unit__ = "minute"


class Resistance(BaseQuantity):
    __base_unit__ = "ohm"


class HeatRate(BaseQuantity):
    __base_unit__ = "Btu/kWh"


class FuelPrice(BaseQuantity):
    __base_unit__ = "usd/Btu"


class VOMPrice(BaseQuantity):
    __base_unit__ = "usd/kWh"


class Energy(BaseQuantity):
    __base_unit__ = "watthour"


class Percentage(BaseQuantity):
    __base_unit__ = "percent"

    def __repr__(self) -> str:
        return f"<Quantity({self.magnitude!r}, '%')>"


class EmissionRate(BaseQuantity):
    __base_unit__ = "kg/MWh"


class PerUnit(BaseQuantity):
    __base_unit__ = "pu"

    def __repr__(self) -> str:
        return f"<Quantity({self.magnitude!r}, 'pu')>"


class PowerRate(BaseQuantity):
    __base_unit__ = "MW/min"


class Currency(BaseQuantity):
    __base_unit__ = "usd"


def get_magnitude(field) -> float | int:
    """Get the numeric magnitude of a quantity-like value."""
    return field.magnitude if isinstance(field, Quantity) else field
