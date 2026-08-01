"""Sparse fast-decoupled AC power-flow algorithm."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import factorized

from o_grid.acpf.models import NumericalSolution, PowerFlowCase
from o_grid.acpf.results import IterationPowerFlowResult
from o_grid.acpf.utils.network import calculate_power


def solve_fast_decoupled(
    case: PowerFlowCase,
    ybus: csc_matrix,
    *,
    tolerance: float,
    max_iterations: int,
    max_angle_step: float = np.deg2rad(5.0),
    max_voltage_step: float = 0.1,
    iteration_callback: Callable[[IterationPowerFlowResult], None] | None = None,
) -> NumericalSolution:
    """Solve an AC case using constant decoupled active/angle and reactive/voltage matrices."""
    voltage = case.initial_voltage.copy()
    specified = case.specified_power
    pq = case.pq_indices
    pv_pq = np.concatenate((case.pv_indices, pq))
    active_matrix, reactive_matrix = _build_decoupled_matrices(ybus)
    active_solver = factorized(active_matrix[pv_pq, :][:, pv_pq])
    reactive_solver = factorized(reactive_matrix[pq, :][:, pq]) if pq.size else None
    trace: list[IterationPowerFlowResult] = []

    for iteration in range(max_iterations + 1):
        calculated = calculate_power(ybus, voltage)
        active_mismatch = specified.real - calculated.real
        reactive_mismatch = specified.imag - calculated.imag
        max_dp = _maximum_absolute(active_mismatch[pv_pq])
        max_dq = _maximum_absolute(reactive_mismatch[pq])
        max_residual = max(max_dp, max_dq)
        if max_residual <= tolerance:
            _append_trace(
                trace, _trace(iteration, max_dp, max_dq, max_residual, 0.0), iteration_callback
            )
            return NumericalSolution(
                voltage=voltage,
                converged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if iteration == max_iterations:
            _append_trace(
                trace, _trace(iteration, max_dp, max_dq, max_residual, 0.0), iteration_callback
            )
            break

        angle_step = np.asarray(active_solver(active_mismatch[pv_pq]))
        angle_step = np.clip(angle_step, -max_angle_step, max_angle_step)
        voltage_step = np.array([], dtype=float)
        if reactive_solver is not None:
            voltage_factor = np.asarray(reactive_solver(reactive_mismatch[pq]))
            voltage_step = np.clip(
                voltage_factor * np.abs(voltage[pq]), -max_voltage_step, max_voltage_step
            )
        voltage, scale = _damped_step(
            case,
            ybus,
            voltage,
            specified,
            pv_pq,
            pq,
            angle_step,
            voltage_step,
            max_residual,
        )
        max_step = max(
            _maximum_absolute(scale * angle_step), _maximum_absolute(scale * voltage_step)
        )
        _append_trace(
            trace, _trace(iteration, max_dp, max_dq, max_residual, max_step), iteration_callback
        )
        magnitude = np.abs(voltage)
        if not np.all(np.isfinite(voltage)) or np.any(magnitude < 0.4) or np.any(magnitude > 2.0):
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration + 1,
                max_mismatch=max_residual,
                trace=trace,
            )

    return NumericalSolution(
        voltage=voltage,
        iterations=max_iterations,
        max_mismatch=trace[-1].max_residual,
        trace=trace,
    )


def _build_decoupled_matrices(ybus: csc_matrix) -> tuple[csc_matrix, csc_matrix]:
    susceptance = -ybus.imag.tocsc()
    return susceptance, susceptance


def _damped_step(
    case: PowerFlowCase,
    ybus: csc_matrix,
    voltage: np.ndarray,
    specified: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
    angle_step: np.ndarray,
    voltage_step: np.ndarray,
    residual: float,
) -> tuple[np.ndarray, float]:
    magnitude = np.abs(voltage)
    angle = np.angle(voltage)
    scale = 1.0
    trial = voltage
    for _ in range(16):
        trial_angle = angle.copy()
        trial_magnitude = magnitude.copy()
        trial_angle[pv_pq] += scale * angle_step
        trial_magnitude[pq] += scale * voltage_step
        voltage_ok = np.all(
            trial_magnitude[pq]
            > np.array([max(0.4, case.buses[index].minimum_voltage * 0.8) for index in pq])
        ) and np.all(
            trial_magnitude[pq]
            < np.array([max(2.0, case.buses[index].maximum_voltage * 1.5) for index in pq])
        )
        trial = trial_magnitude * np.exp(1j * trial_angle)
        calculated = calculate_power(ybus, trial)
        mismatch = np.concatenate(
            ((specified.real - calculated.real)[pv_pq], (specified.imag - calculated.imag)[pq])
        )
        if voltage_ok and (_maximum_absolute(mismatch) <= residual or scale < 1e-4):
            return trial, scale
        scale *= 0.5
    return trial, scale


def _trace(
    iteration: int, max_dp: float, max_dq: float, max_residual: float, max_step: float
) -> IterationPowerFlowResult:
    return IterationPowerFlowResult(
        iteration=iteration,
        max_dp=max_dp,
        max_dq=max_dq,
        max_control_residual=0.0,
        max_residual=max_residual,
        max_step=max_step,
    )


def _append_trace(
    trace: list[IterationPowerFlowResult],
    item: IterationPowerFlowResult,
    callback: Callable[[IterationPowerFlowResult], None] | None,
) -> None:
    trace.append(item)
    if callback is not None:
        callback(item)


def _maximum_absolute(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0
