"""Sparse fast-decoupled AC power-flow algorithm."""

from __future__ import annotations

import numpy as np
from scipy.sparse import csc_matrix, lil_matrix
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
) -> NumericalSolution:
    """Solve an AC case using constant decoupled active/angle and reactive/voltage matrices."""
    voltage = case.initial_voltage.copy()
    specified = case.specified_power
    pq = case.pq_indices
    pv_pq = np.concatenate((case.pv_indices, pq))
    active_matrix, reactive_matrix = _build_decoupled_matrices(case, ybus)
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
            trace.append(_trace(iteration, max_dp, max_dq, max_residual, 0.0))
            return NumericalSolution(
                voltage=voltage,
                converged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if iteration == max_iterations:
            trace.append(_trace(iteration, max_dp, max_dq, max_residual, 0.0))
            break

        magnitude = np.abs(voltage)
        angle_step = np.asarray(active_solver(active_mismatch[pv_pq] / magnitude[pv_pq]))
        voltage, angle_scale = _damped_angle_step(
            ybus, voltage, specified, pv_pq, angle_step, max_dp
        )

        calculated = calculate_power(ybus, voltage)
        reactive_mismatch = specified.imag - calculated.imag
        magnitude = np.abs(voltage)
        voltage_step = np.array([], dtype=float)
        voltage_scale = 0.0
        if reactive_solver is not None:
            voltage_step = np.asarray(reactive_solver(reactive_mismatch[pq] / magnitude[pq]))
            voltage, voltage_scale = _damped_voltage_step(
                ybus,
                voltage,
                specified,
                pq,
                voltage_step,
                _maximum_absolute(reactive_mismatch[pq]),
            )
        max_step = max(
            _maximum_absolute(angle_scale * angle_step),
            _maximum_absolute(voltage_scale * voltage_step),
        )
        trace.append(_trace(iteration, max_dp, max_dq, max_residual, max_step))
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


def _build_decoupled_matrices(
    case: PowerFlowCase, ybus: csc_matrix
) -> tuple[csc_matrix, csc_matrix]:
    active = lil_matrix(ybus.shape, dtype=float)
    indices = case.bus_index
    for branch in case.branches:
        if abs(branch.reactance) <= 1e-12:
            continue
        from_index = indices[branch.from_bus]
        to_index = indices[branch.to_bus]
        susceptance = 1.0 / branch.reactance
        active[from_index, from_index] += susceptance
        active[to_index, to_index] += susceptance
        active[from_index, to_index] -= susceptance
        active[to_index, from_index] -= susceptance
    return active.tocsc(), -ybus.imag.tocsc()


def _damped_angle_step(
    ybus: csc_matrix,
    voltage: np.ndarray,
    specified: np.ndarray,
    pv_pq: np.ndarray,
    step: np.ndarray,
    residual: float,
) -> tuple[np.ndarray, float]:
    magnitude = np.abs(voltage)
    angle = np.angle(voltage)
    scale = 1.0
    for _ in range(14):
        trial_angle = angle.copy()
        trial_angle[pv_pq] += scale * step
        trial = magnitude * np.exp(1j * trial_angle)
        mismatch = specified.real - calculate_power(ybus, trial).real
        if _maximum_absolute(mismatch[pv_pq]) < residual:
            return trial, scale
        scale *= 0.5
    return voltage, 0.0


def _damped_voltage_step(
    ybus: csc_matrix,
    voltage: np.ndarray,
    specified: np.ndarray,
    pq: np.ndarray,
    step: np.ndarray,
    residual: float,
) -> tuple[np.ndarray, float]:
    magnitude = np.abs(voltage)
    angle = np.angle(voltage)
    scale = 1.0
    for _ in range(14):
        trial_magnitude = magnitude.copy()
        trial_magnitude[pq] = np.clip(trial_magnitude[pq] + scale * step, 0.5, 1.5)
        trial = trial_magnitude * np.exp(1j * angle)
        mismatch = specified.imag - calculate_power(ybus, trial).imag
        if _maximum_absolute(mismatch[pq]) < residual:
            return trial, scale
        scale *= 0.5
    return voltage, 0.0


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


def _maximum_absolute(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0
