"""Sparse full Newton-Raphson AC power-flow algorithm."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.sparse import csc_matrix, diags, hstack, vstack
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from o_grid.acpf.models import NumericalSolution, PowerFlowCase
from o_grid.acpf.results import IterationPowerFlowResult
from o_grid.acpf.utils.network import calculate_power


def solve_newton_raphson(
    case: PowerFlowCase,
    ybus: csc_matrix,
    *,
    tolerance: float,
    max_iterations: int,
    initial_voltage: np.ndarray | None = None,
    iteration_callback: Callable[[IterationPowerFlowResult], None] | None = None,
) -> NumericalSolution:
    """Solve an AC case with a sparse polar-coordinate Newton-Raphson method."""
    voltage = case.initial_voltage.copy() if initial_voltage is None else initial_voltage.copy()
    specified = case.specified_power
    pq = case.pq_indices
    pv_pq = np.concatenate((case.pv_indices, pq))
    if initial_voltage is None and max_iterations > 0:
        parsed_seed = _warm_start_angles(ybus, voltage, specified, pv_pq, pq)
        flat_seed = _warm_start_angles(
            ybus,
            np.abs(voltage).astype(np.complex128),
            specified,
            pv_pq,
            pq,
        )
        parsed_residual = _maximum_absolute(
            specified.real[pv_pq] - calculate_power(ybus, parsed_seed).real[pv_pq]
        )
        flat_residual = _maximum_absolute(
            specified.real[pv_pq] - calculate_power(ybus, flat_seed).real[pv_pq]
        )
        voltage = flat_seed if flat_residual < parsed_residual else parsed_seed
    trace: list[IterationPowerFlowResult] = []

    for iteration in range(max_iterations + 1):
        calculated = calculate_power(ybus, voltage)
        active_mismatch = specified.real - calculated.real
        reactive_mismatch = specified.imag - calculated.imag
        mismatch = np.concatenate((active_mismatch[pv_pq], reactive_mismatch[pq]))
        max_dp = _maximum_absolute(active_mismatch[pv_pq])
        max_dq = _maximum_absolute(reactive_mismatch[pq])
        max_residual = _maximum_absolute(mismatch)

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

        jacobian = _build_jacobian(ybus, voltage, pv_pq, pq)
        try:
            with np.errstate(all="raise"):
                step = np.asarray(spsolve(jacobian, mismatch), dtype=float)
        except (MatrixRankWarning, FloatingPointError, RuntimeError, ValueError):
            item = _trace(iteration, max_dp, max_dq, max_residual, 0.0)
            _append_trace(trace, item, iteration_callback)
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if not np.all(np.isfinite(step)):
            item = _trace(iteration, max_dp, max_dq, max_residual, 0.0)
            _append_trace(trace, item, iteration_callback)
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )

        voltage, scale = _line_search(case, ybus, voltage, specified, pv_pq, pq, step, max_residual)
        max_step = _maximum_absolute(scale * step)
        _append_trace(
            trace, _trace(iteration, max_dp, max_dq, max_residual, max_step), iteration_callback
        )
        magnitudes = np.abs(voltage)
        if np.any(magnitudes < 0.4) or np.any(magnitudes > 2.0):
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


def _build_jacobian(
    ybus: csc_matrix, voltage: np.ndarray, pv_pq: np.ndarray, pq: np.ndarray
) -> csc_matrix:
    voltage_magnitude = np.abs(voltage)
    normalized_voltage = np.divide(
        voltage,
        voltage_magnitude,
        out=np.ones_like(voltage),
        where=voltage_magnitude > 0.0,
    )
    current = ybus @ voltage
    diagonal_voltage = diags(voltage, format="csc")
    diagonal_current = diags(current, format="csc")
    diagonal_normalized = diags(normalized_voltage, format="csc")
    d_power_d_magnitude = diagonal_voltage @ (ybus @ diagonal_normalized).conjugate()
    d_power_d_magnitude += diagonal_current.conjugate() @ diagonal_normalized
    d_power_d_angle = (
        1j * diagonal_voltage @ (diagonal_current - ybus @ diagonal_voltage).conjugate()
    )

    j11 = d_power_d_angle[pv_pq, :][:, pv_pq].real
    j12 = d_power_d_magnitude[pv_pq, :][:, pq].real
    j21 = d_power_d_angle[pq, :][:, pv_pq].imag
    j22 = d_power_d_magnitude[pq, :][:, pq].imag
    return vstack((hstack((j11, j12)), hstack((j21, j22))), format="csc")


def _line_search(
    case: PowerFlowCase,
    ybus: csc_matrix,
    voltage: np.ndarray,
    specified: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
    step: np.ndarray,
    current_residual: float,
) -> tuple[np.ndarray, float]:
    angle = np.angle(voltage)
    magnitude = np.abs(voltage)
    angle_count = len(pv_pq)
    scale = 1.0
    trial = voltage
    for _ in range(16):
        trial_angle = angle.copy()
        trial_magnitude = magnitude.copy()
        trial_angle[pv_pq] += scale * step[:angle_count]
        trial_magnitude[pq] += scale * step[angle_count:]
        trial_magnitude[pq] = np.clip(
            trial_magnitude[pq],
            [max(0.5, case.buses[index].minimum_voltage * 0.8) for index in pq],
            [max(1.5, case.buses[index].maximum_voltage * 1.5) for index in pq],
        )
        trial = trial_magnitude * np.exp(1j * trial_angle)
        calculated = calculate_power(ybus, trial)
        mismatch = np.concatenate(
            ((specified.real - calculated.real)[pv_pq], (specified.imag - calculated.imag)[pq])
        )
        if _maximum_absolute(mismatch) <= current_residual or scale < 1e-4:
            return trial, scale
        scale *= 0.5
    return trial, scale


def _warm_start_angles(
    ybus: csc_matrix,
    voltage: np.ndarray,
    specified: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
) -> np.ndarray:
    if not pv_pq.size:
        return voltage
    for _ in range(24):
        calculated = calculate_power(ybus, voltage)
        mismatch = specified.real[pv_pq] - calculated.real[pv_pq]
        if _maximum_absolute(mismatch) <= 0.1:
            break
        jacobian = _build_jacobian(ybus, voltage, pv_pq, pq)[: len(pv_pq), : len(pv_pq)]
        try:
            step = np.asarray(spsolve(jacobian, mismatch), dtype=float)
        except (MatrixRankWarning, FloatingPointError, RuntimeError, ValueError):
            break
        if not np.all(np.isfinite(step)):
            break
        angle = np.angle(voltage)
        magnitude = np.abs(voltage)
        current_norm = float(np.linalg.norm(mismatch))
        accepted = False
        scale = 1.0
        for _ in range(8):
            trial_angle = angle.copy()
            trial_angle[pv_pq] += scale * step
            trial = magnitude * np.exp(1j * trial_angle)
            trial_mismatch = specified.real[pv_pq] - calculate_power(ybus, trial).real[pv_pq]
            if float(np.linalg.norm(trial_mismatch)) < current_norm:
                voltage = trial
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            break
    return voltage


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
