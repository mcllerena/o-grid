"""Sparse full Newton-Raphson AC power-flow algorithm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np
from scipy.sparse import csc_matrix, diags, hstack, vstack
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from o_grid.acpf.models import NumericalSolution, PowerFlowCase
from o_grid.acpf.models.svc import (
    build_svc_states,
    svc_control_derivative_q,
    svc_control_derivative_voltage,
    svc_q_injection_by_bus,
    sync_svc_states_to_case,
    update_svc_limits,
)
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
    control_callback: Callable[[np.ndarray, csc_matrix], tuple[np.ndarray, csc_matrix]]
    | None = None,
) -> NumericalSolution:
    """Solve an AC case with a sparse polar-coordinate Newton-Raphson method.

    Active PQ-bus SVC devices are embedded in the Newton state vector as reactive
    injections with control/limit residual rows, following the reference DCER model.
    """
    voltage = case.initial_voltage.copy() if initial_voltage is None else initial_voltage.copy()
    specified = case.specified_power
    pq = case.pq_indices
    pv_pq = np.concatenate((case.pv_indices, pq))
    svc_states = build_svc_states(case, voltage)
    specified_no_svc = _without_svc_injection(case, specified, svc_states)
    active_svc = np.array(
        [index for index, state in enumerate(svc_states) if state.active], dtype=np.int64
    )
    if initial_voltage is None and max_iterations > 0:
        parsed_seed = _warm_start_angles(ybus, voltage, specified_no_svc, pv_pq, pq)
        flat_seed = _warm_start_angles(
            ybus,
            np.abs(voltage).astype(np.complex128),
            specified_no_svc,
            pv_pq,
            pq,
        )
        parsed_dp = _maximum_absolute(
            specified_no_svc.real[pv_pq] - calculate_power(ybus, parsed_seed).real[pv_pq]
        )
        parsed_dq = _maximum_absolute(
            specified_no_svc.imag[pq] - calculate_power(ybus, parsed_seed).imag[pq]
        )
        flat_dp = _maximum_absolute(
            specified_no_svc.real[pv_pq] - calculate_power(ybus, flat_seed).real[pv_pq]
        )
        flat_dq = _maximum_absolute(
            specified_no_svc.imag[pq] - calculate_power(ybus, flat_seed).imag[pq]
        )
        voltage = flat_seed if flat_dp + flat_dq < parsed_dp + parsed_dq else parsed_seed
    trace: list[IterationPowerFlowResult] = []

    for iteration in range(max_iterations + 1):
        if control_callback is not None:
            voltage, ybus = control_callback(voltage, ybus)
            specified = case.specified_power
        calculated = calculate_power(ybus, voltage)
        svc_injection = svc_q_injection_by_bus(svc_states, len(case.buses))
        active_mismatch = specified_no_svc.real - calculated.real
        reactive_mismatch = specified_no_svc.imag + svc_injection - calculated.imag
        control_residual = -np.array(
            [svc_states[index].control_residual for index in active_svc], dtype=float
        )
        mismatch = np.concatenate((active_mismatch[pv_pq], reactive_mismatch[pq], control_residual))
        max_dp = _maximum_absolute(active_mismatch[pv_pq])
        max_dq = _maximum_absolute(reactive_mismatch[pq])
        max_control = _maximum_absolute(control_residual)
        max_residual = _maximum_absolute(mismatch)

        if max_residual <= tolerance:
            _append_trace(
                trace,
                _trace(iteration, max_dp, max_dq, max_control, max_residual, 0.0),
                iteration_callback,
            )
            sync_svc_states_to_case(case, svc_states)
            return NumericalSolution(
                voltage=voltage,
                converged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if iteration == max_iterations:
            _append_trace(
                trace,
                _trace(iteration, max_dp, max_dq, max_control, max_residual, 0.0),
                iteration_callback,
            )
            break

        jacobian = _build_jacobian(
            ybus, voltage, pv_pq, pq, svc_states, active_svc, np.abs(voltage)
        )
        try:
            with np.errstate(all="raise"):
                step = np.asarray(spsolve(jacobian, mismatch), dtype=float)
        except (MatrixRankWarning, FloatingPointError, RuntimeError, ValueError):
            item = _trace(iteration, max_dp, max_dq, max_control, max_residual, 0.0)
            _append_trace(trace, item, iteration_callback)
            sync_svc_states_to_case(case, svc_states)
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if not np.all(np.isfinite(step)):
            item = _trace(iteration, max_dp, max_dq, max_control, max_residual, 0.0)
            _append_trace(trace, item, iteration_callback)
            sync_svc_states_to_case(case, svc_states)
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )

        voltage, svc_states, scale = _line_search(
            case,
            ybus,
            voltage,
            svc_states,
            active_svc,
            specified_no_svc,
            pv_pq,
            pq,
            step,
            max_residual,
        )
        max_step = _maximum_absolute(scale * step)
        _append_trace(
            trace,
            _trace(iteration, max_dp, max_dq, max_control, max_residual, max_step),
            iteration_callback,
        )
        magnitudes = np.abs(voltage)
        if np.any(magnitudes < 0.4) or np.any(magnitudes > 2.0):
            sync_svc_states_to_case(case, svc_states)
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration + 1,
                max_mismatch=max_residual,
                trace=trace,
            )

    sync_svc_states_to_case(case, svc_states)
    return NumericalSolution(
        voltage=voltage,
        iterations=max_iterations,
        max_mismatch=trace[-1].max_residual,
        trace=trace,
    )


def _without_svc_injection(
    case: PowerFlowCase, specified: np.ndarray, svc_states: list
) -> np.ndarray:
    """Remove the SVC reactive injection baked into bus generation from the schedule."""
    injection = svc_q_injection_by_bus(svc_states, len(case.buses))
    return specified - 1j * injection


def _build_jacobian(
    ybus: csc_matrix,
    voltage: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
    svc_states: list | None = None,
    active_svc: np.ndarray | None = None,
    magnitudes: np.ndarray | None = None,
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

    if not svc_states or active_svc is None or active_svc.size == 0:
        return vstack((hstack((j11, j12)), hstack((j21, j22))), format="csc")

    magnitude = voltage_magnitude if magnitudes is None else magnitudes
    pq_column = {int(index): column for column, index in enumerate(pq)}
    base_jacobian = vstack(
        (
            hstack((j11, j12), format="csc"),
            hstack((j21, j22), format="csc"),
        ),
        format="csc",
    )
    svc_voltage_rows: list[int] = []
    svc_voltage_columns: list[int] = []
    svc_voltage_values: list[float] = []
    svc_q_rows: list[int] = []
    svc_q_columns: list[int] = []
    svc_q_values: list[float] = []
    control_q_values: list[float] = []
    for column, index in enumerate(active_svc.tolist()):
        state = svc_states[index]
        q_row = pq_column.get(state.bus_index)
        if q_row is not None:
            svc_q_rows.append(len(pv_pq) + q_row)
            svc_q_columns.append(column)
            svc_q_values.append(-1.0)
        control_row = column
        control_column = pq_column.get(state.control_bus_index)
        if control_column is not None:
            svc_voltage_rows.append(control_row)
            svc_voltage_columns.append(len(pv_pq) + control_column)
            svc_voltage_values.append(
                svc_control_derivative_voltage(state, state.control_bus_index, magnitude)
            )
        device_column = pq_column.get(state.bus_index)
        if device_column is not None:
            svc_voltage_rows.append(control_row)
            svc_voltage_columns.append(len(pv_pq) + device_column)
            svc_voltage_values.append(
                svc_control_derivative_voltage(state, state.bus_index, magnitude)
            )
        control_q_values.append(svc_control_derivative_q(state, magnitude))
    svc_voltage = csc_matrix(
        (svc_voltage_values, (svc_voltage_rows, svc_voltage_columns)),
        shape=(len(active_svc), len(pv_pq) + len(pq)),
    )
    svc_q = csc_matrix(
        (svc_q_values, (svc_q_rows, svc_q_columns)),
        shape=(len(pv_pq) + len(pq), len(active_svc)),
    )
    control_rows = hstack((svc_voltage, diags(control_q_values, format="csc")), format="csc")
    return vstack((hstack((base_jacobian, svc_q), format="csc"), control_rows), format="csc")


def _line_search(
    case: PowerFlowCase,
    ybus: csc_matrix,
    voltage: np.ndarray,
    svc_states: list,
    active_svc: np.ndarray,
    specified: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
    step: np.ndarray,
    current_residual: float,
) -> tuple[np.ndarray, list, float]:
    angle = np.angle(voltage)
    magnitude = np.abs(voltage)
    angle_count = len(pv_pq)
    magnitude_count = len(pq)
    scale = 1.0
    trial = voltage
    for _ in range(16):
        trial_angle = angle.copy()
        trial_magnitude = magnitude.copy()
        trial_states = [replace(state) for state in svc_states]
        trial_angle[pv_pq] += scale * step[:angle_count]
        trial_magnitude[pq] += scale * step[angle_count : angle_count + magnitude_count]
        trial_magnitude[pq] = np.clip(
            trial_magnitude[pq],
            [max(0.5, case.buses[index].minimum_voltage * 0.8) for index in pq],
            [max(1.5, case.buses[index].maximum_voltage * 1.5) for index in pq],
        )
        for column, index in enumerate(active_svc):
            trial_states[index].q_pu += scale * step[angle_count + magnitude_count + column]
        update_svc_limits(trial_states, trial_magnitude)
        trial = trial_magnitude * np.exp(1j * trial_angle)
        calculated = calculate_power(ybus, trial)
        trial_injection = svc_q_injection_by_bus(trial_states, len(case.buses))
        mismatch = np.concatenate(
            (
                (specified.real - calculated.real)[pv_pq],
                (specified.imag + trial_injection - calculated.imag)[pq],
                -np.array(
                    [trial_states[index].control_residual for index in active_svc], dtype=float
                ),
            )
        )
        if _maximum_absolute(mismatch) <= current_residual or scale < 1e-4:
            return trial, trial_states, scale
        scale *= 0.5
    return trial, trial_states, scale


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
    iteration: int,
    max_dp: float,
    max_dq: float,
    max_control_residual: float,
    max_residual: float,
    max_step: float,
) -> IterationPowerFlowResult:
    return IterationPowerFlowResult(
        iteration=iteration,
        max_dp=max_dp,
        max_dq=max_dq,
        max_control_residual=max_control_residual,
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
