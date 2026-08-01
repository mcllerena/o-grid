"""Infrasys components containing AC power-flow result fields."""

from __future__ import annotations

from infrasys import Component
from pydantic import BaseModel, Field

from o_grid.acpf.results import IterationPowerFlowResult


class StatisticResultsInformation(Component):
    """Solver statistics attached to a solved infrasys system."""

    source_path: str
    solver: str
    solver_mode: str
    converged: bool
    diverged: bool
    iterations: int
    max_mismatch_pu: float | None
    base_mva: float
    estimated_dense_matrix_memory_gb: float
    convergence_tolerance_pu: float
    divergence_voltage_minimum_pu: float
    divergence_voltage_maximum_pu: float
    near_zero_guard_tolerance: float
    scheduled_generation_mw: float
    solved_generation_mw: float
    total_load_mw: float
    branch_active_losses_mw: float
    power_balance_mw: float
    bus_count: int
    bus_count_after_reduction: int
    branch_count: int
    branch_count_after_reduction: int
    ac_line_count: int
    ltc_count: int
    phase_shifting_transformer_count: int
    switch_count: int
    dc_line_count: int
    static_var_compensator_count: int
    controllable_series_compensator_count: int
    voltage_upper_violations: int
    voltage_lower_violations: int
    line_flow_overloads: int
    iteration_trace: list[IterationPowerFlowResult] = Field(default_factory=list)


ResultsInformation = StatisticResultsInformation


class ACBusResults(Component):
    """Solved fields corresponding to the workbook Buses sheet."""

    bus_number: int
    bus_name: str
    bus_type: str
    area: int | str | None
    in_service: bool
    voltage_pu: float
    voltage_kv: float | None
    angle_deg: float
    active_generation_mw: float
    reactive_generation_mvar: float
    active_load_mw: float
    reactive_load_mvar: float
    minimum_voltage_pu: float
    maximum_voltage_pu: float
    violation: str | None
    representative_bus: int
    collapsed: bool


class GeneratorResults(Component):
    """Solved generator output, technology, limits, and reserve."""

    bus_number: int
    bus_name: str
    generator_type: str
    active_generation_mw: float
    reactive_generation_mvar: float
    maximum_active_generation_mw: float | None
    reserve_mw: float | None
    voltage_pu: float
    angle_deg: float


class ACLineResults(Component):
    """Solved fields corresponding to the workbook Lines sheet."""

    line_number: int
    from_bus: int
    to_bus: int
    circuit: int
    resistance_pu: float
    reactance_pu: float
    charging_pu: float
    tap_pu: float
    phase_shift_deg: float
    rating_mva: float
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str
    loading_percent: float
    active_loss_mw: float
    reactive_loss_mvar: float
    violation: bool


class TransformerResults(Component):
    """Solved fields for fixed-ratio transformers."""

    device_number: int
    from_bus: int
    to_bus: int
    circuit: int
    resistance_pu: float
    reactance_pu: float
    tap_pu: float
    phase_shift_deg: float
    rating_mva: float
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str
    loading_percent: float
    active_loss_mw: float
    reactive_loss_mvar: float
    violation: bool


class LTCTransformerResults(Component):
    """Solved fields corresponding to the workbook LTC sheet."""

    device_number: int
    from_bus: int
    to_bus: int
    circuit: int
    controlled_bus: int | None
    tap_pu: float
    minimum_tap_pu: float | None
    maximum_tap_pu: float | None
    target_voltage_pu: float | None
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str


class PhaseShiftingTransformerResults(Component):
    """Solved fields corresponding to the workbook PST sheet."""

    device_number: int
    from_bus: int
    to_bus: int
    circuit: int
    controlled_bus: int | None
    phase_shift_deg: float
    minimum_phase_shift_deg: float | None
    maximum_phase_shift_deg: float | None
    target_active_power_mw: float | None
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str


class SwitchDeviceResults(Component):
    """Solved switch status and terminal flows."""

    device_number: int
    from_bus: int
    to_bus: int
    circuit: int
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str
    loading_percent: float
    active_loss_mw: float
    reactive_loss_mvar: float
    status: str


class StaticVARCompensatorResults(Component):
    """Solved fields corresponding to the workbook SVC sheet."""

    device_number: int
    bus_number: int
    bus_name: str
    controlled_bus: int | None
    mode: str
    voltage_pu: float
    reference_voltage_pu: float | None
    slope_percent: float | None
    reactive_power_mvar: float
    initial_reactive_power_mvar: float
    reactive_power_delta_mvar: float
    minimum_reactive_power_mvar: float | None
    maximum_reactive_power_mvar: float | None
    status: str
    equation_residual: float | None


class ControllableSeriesCompensatorResults(Component):
    """Solved fields corresponding to the workbook CSC sheet."""

    device_number: int
    from_bus: int
    to_bus: int
    circuit: int
    mode: str
    reactance_pu: float
    minimum_reactance_pu: float | None
    maximum_reactance_pu: float | None
    active_from_mw: float
    reactive_from_mvar: float
    active_to_mw: float
    reactive_to_mvar: float
    power_factor_from: float
    reactive_type_from: str
    power_factor_to: float
    reactive_type_to: str
    status: str


class DCLineResults(Component):
    """Solved fields corresponding to the workbook HVDC sheet."""

    bus_number: int | None
    bus_name: str | None
    voltage_pu: float | None
    converter_type: str | None
    pole_number: int | None
    control_mode: str | None
    active_power_mw: float | None
    reactive_power_mvar: float | None
    loss_mw: float | None
    dc_voltage_kv: float | None
    dc_current_pu: float | None
    dc_current_a: float | None
    firing_angle_deg: float | None
    overlap_angle_deg: float | None
    power_factor_angle_deg: float | None
    tap_pu: float | None
    status: str


ResultComponent = (
    StatisticResultsInformation
    | ACBusResults
    | GeneratorResults
    | ACLineResults
    | TransformerResults
    | LTCTransformerResults
    | PhaseShiftingTransformerResults
    | SwitchDeviceResults
    | StaticVARCompensatorResults
    | ControllableSeriesCompensatorResults
    | DCLineResults
)


class PowerFlowResults(BaseModel):
    """Typed access to every result component attached to a system."""

    information: StatisticResultsInformation
    ac_buses: list[ACBusResults] = Field(default_factory=list)
    generators: list[GeneratorResults] = Field(default_factory=list)
    ac_lines: list[ACLineResults] = Field(default_factory=list)
    transformers: list[TransformerResults] = Field(default_factory=list)
    ltc_transformers: list[LTCTransformerResults] = Field(default_factory=list)
    phase_shifting_transformers: list[PhaseShiftingTransformerResults] = Field(default_factory=list)
    switch_devices: list[SwitchDeviceResults] = Field(default_factory=list)
    static_var_compensators: list[StaticVARCompensatorResults] = Field(default_factory=list)
    controllable_series_compensators: list[ControllableSeriesCompensatorResults] = Field(
        default_factory=list
    )
    dc_lines: list[DCLineResults] = Field(default_factory=list)

    def components(self) -> list[ResultComponent]:
        """Return all result rows, including the summary component."""
        return [
            self.information,
            *self.ac_buses,
            *self.generators,
            *self.ac_lines,
            *self.transformers,
            *self.ltc_transformers,
            *self.phase_shifting_transformers,
            *self.switch_devices,
            *self.static_var_compensators,
            *self.controllable_series_compensators,
            *self.dc_lines,
        ]


RESULT_COMPONENT_TYPES = (
    StatisticResultsInformation,
    ACBusResults,
    GeneratorResults,
    ACLineResults,
    TransformerResults,
    LTCTransformerResults,
    PhaseShiftingTransformerResults,
    SwitchDeviceResults,
    StaticVARCompensatorResults,
    ControllableSeriesCompensatorResults,
    DCLineResults,
)
