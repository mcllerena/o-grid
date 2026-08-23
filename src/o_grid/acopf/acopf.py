"""Primal-dual barrier method for the AC power-flow subproblem."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.sparse import csc_matrix

from o_grid.acpf.models import NumericalSolution, PowerFlowCase
from o_grid.acpf.newton_raphson import solve_newton_raphson
from o_grid.acpf.results import IterationPowerFlowResult
from o_grid.acpf.utils.network import calculate_power

_EPSILON = 1.0e-10
_INTERIOR_MARGIN = 1.0e-8
_MAX_STATE_STEP = 0.25
_MIN_PHYSICAL_VOLTAGE = 0.5
_MAX_PHYSICAL_VOLTAGE = 1.5


def solve_acopf(
    case: PowerFlowCase,
    ybus: csc_matrix,
    *,
    tolerance: float,
    max_iterations: int,
    initial_voltage: np.ndarray | None = None,
    iteration_callback: Callable[[IterationPowerFlowResult], None] | None = None,
    initial_mu: float = 5.0,
    minimum_mu: float = 5.0e-4,
    reduction_parameter: float = 10.0,
    safety_factor: float = 0.9995,
) -> NumericalSolution:
    """Solve the bounded AC power-flow feasibility subproblem.

    The nonlinear equality constraints are the active and reactive AC balance
    equations. Voltage angles and non-reference voltage magnitudes are the
    only bounded primal variables. The quadratic term keeps the solution near
    the parsed operating point. Generation, controls, operating costs, and
    branch security constraints are not decision variables in this routine.
    """
    voltage = case.initial_voltage.copy() if initial_voltage is None else initial_voltage.copy()
    voltage = _feasible_voltage_seed(case, ybus, voltage, max_iterations)
    variable_indices, angle_indices, magnitude_indices = _variable_indices(case)
    reference = _state_from_voltage(voltage, angle_indices, magnitude_indices)
    lower, upper = _state_bounds(case, angle_indices, magnitude_indices)
    state = np.clip(reference, lower + 1.0e-6, upper - 1.0e-6)
    voltage = _voltage_from_state(case, state, angle_indices, magnitude_indices, voltage)
    residual_size = len(case.pv_indices) + len(case.pq_indices) + len(case.pq_indices)
    if variable_indices.size == 0 or residual_size == 0:
        return NumericalSolution(voltage=voltage, converged=True, max_mismatch=0.0)

    slack_lower = state - lower
    slack_upper = upper - state
    dual_lower = np.full(state.size, initial_mu / max(float(np.mean(slack_lower)), 1.0))
    dual_upper = np.full(state.size, initial_mu / max(float(np.mean(slack_upper)), 1.0))
    multipliers = np.zeros(residual_size)
    trace: list[IterationPowerFlowResult] = []
    mu = initial_mu

    for iteration in range(max_iterations + 1):
        equality = _balance_residual(case, ybus, state, angle_indices, magnitude_indices)
        jacobian = _finite_difference_jacobian(
            lambda trial: _balance_residual(case, ybus, trial, angle_indices, magnitude_indices),
            state,
            lower,
            upper,
        )
        gradient = state - reference
        stationarity = gradient - jacobian.T @ multipliers - dual_lower + dual_upper
        max_dp, max_dq = _balance_metrics(case, equality)
        max_residual = float(
            max(
                np.max(np.abs(equality), initial=0.0),
                np.max(np.abs(stationarity), initial=0.0),
            )
        )
        max_step = 0.0
        if (
            mu <= 5.1e-4
            and max_dp <= tolerance
            and max_dq <= tolerance
            and np.max(np.abs(stationarity)) <= 1.0e-4
        ):
            _emit(
                trace,
                iteration,
                max_dp,
                max_dq,
                max_residual,
                max_step,
                iteration_callback,
            )
            return NumericalSolution(
                voltage=voltage,
                converged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        if iteration == max_iterations:
            _emit(
                trace,
                iteration,
                max_dp,
                max_dq,
                max_residual,
                max_step,
                iteration_callback,
            )
            break

        hessian = jacobian.T @ jacobian + np.eye(state.size)
        rhs_state = (
            -stationarity
            + dual_lower / slack_lower * (mu - slack_lower * dual_lower)
            - dual_upper / slack_upper * (mu - slack_upper * dual_upper)
        )
        kkt = np.block(
            [
                [hessian, -jacobian.T],
                [jacobian, np.zeros((equality.size, equality.size))],
            ]
        )
        rhs = np.concatenate((rhs_state, -equality))
        try:
            direction = np.linalg.solve(kkt, rhs)
        except np.linalg.LinAlgError:
            direction = np.linalg.lstsq(kkt, rhs, rcond=None)[0]
        if not np.all(np.isfinite(direction)):
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )

        state_step = direction[: state.size]
        multiplier_step = direction[state.size :]
        lower_dual_step = (mu - slack_lower * dual_lower - dual_lower * state_step) / slack_lower
        upper_dual_step = (mu - slack_upper * dual_upper + dual_upper * state_step) / slack_upper
        primal_step = min(
            _interior_step(state, state_step, lower, upper, safety_factor),
            _trust_step(state_step, _MAX_STATE_STEP),
        )
        dual_step = _positive_step(
            np.concatenate((dual_lower, dual_upper)),
            np.concatenate((lower_dual_step, upper_dual_step)),
            safety_factor,
        )
        dual_step = min(dual_step, _trust_step(multiplier_step, _MAX_STATE_STEP))
        accepted_step, accepted_state = _accept_state_step(
            case,
            ybus,
            state,
            state_step,
            primal_step,
            equality,
            jacobian,
            lower,
            upper,
            angle_indices,
            magnitude_indices,
        )
        if accepted_step == 0.0:
            return NumericalSolution(
                voltage=voltage,
                diverged=True,
                iterations=iteration,
                max_mismatch=max_residual,
                trace=trace,
            )
        primal_step = accepted_step
        state = accepted_state
        multipliers += dual_step * multiplier_step
        dual_update = np.concatenate((dual_lower, dual_upper)) + dual_step * np.concatenate(
            (lower_dual_step, upper_dual_step)
        )
        dual_lower = np.maximum(dual_update[: state.size], _EPSILON)
        dual_upper = np.maximum(dual_update[state.size :], _EPSILON)
        slack_lower = state - lower
        slack_upper = upper - state
        voltage = _voltage_from_state(case, state, angle_indices, magnitude_indices, voltage)
        max_step = float(
            max(
                np.max(np.abs(primal_step * state_step), initial=0.0),
                dual_step * np.max(np.abs(multiplier_step), initial=0.0),
            )
        )
        _emit(
            trace,
            iteration,
            max_dp,
            max_dq,
            max_residual,
            max_step,
            iteration_callback,
        )
        mu = max(minimum_mu, mu / reduction_parameter)

    return NumericalSolution(
        voltage=voltage,
        max_mismatch=float(trace[-1].max_residual) if trace else None,
        iterations=max_iterations,
        trace=trace,
    )


def _variable_indices(case: PowerFlowCase) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    angle_indices = np.concatenate((case.pv_indices, case.pq_indices)).astype(np.int64)
    magnitude_indices = case.pq_indices.astype(np.int64)
    return np.concatenate((angle_indices, magnitude_indices)), angle_indices, magnitude_indices


def _feasible_voltage_seed(
    case: PowerFlowCase,
    ybus: csc_matrix,
    voltage: np.ndarray,
    max_iterations: int,
) -> np.ndarray:
    """Obtain a feasible AC state before following the primal-dual path."""
    initial_state = _variable_indices(case)
    initial_residual = _balance_residual(
        case,
        ybus,
        _state_from_voltage(voltage, initial_state[1], initial_state[2]),
        initial_state[1],
        initial_state[2],
    )
    if np.max(np.abs(initial_residual), initial=0.0) <= 1.0:
        return voltage
    warm_start = solve_newton_raphson(
        case,
        ybus,
        tolerance=1.0e-6,
        max_iterations=min(max_iterations, 20),
        initial_voltage=voltage,
    )
    return warm_start.voltage if warm_start.converged else voltage


def _state_from_voltage(
    voltage: np.ndarray, angles: np.ndarray, magnitudes: np.ndarray
) -> np.ndarray:
    return np.concatenate((np.angle(voltage)[angles], np.abs(voltage)[magnitudes]))


def _state_bounds(
    case: PowerFlowCase, angles: np.ndarray, magnitudes: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    angle_lower = np.full(angles.size, -np.pi)
    angle_upper = np.full(angles.size, np.pi)
    del case
    magnitude_lower = np.full(magnitudes.size, _MIN_PHYSICAL_VOLTAGE)
    magnitude_upper = np.full(magnitudes.size, _MAX_PHYSICAL_VOLTAGE)
    return (
        np.concatenate((angle_lower, magnitude_lower)),
        np.concatenate((angle_upper, magnitude_upper)),
    )


def _voltage_from_state(
    case: PowerFlowCase,
    state: np.ndarray,
    angles: np.ndarray,
    magnitudes: np.ndarray,
    current: np.ndarray,
) -> np.ndarray:
    del case
    voltage = current.copy()
    voltage[angles] = np.abs(voltage[angles]) * np.exp(1j * state[: angles.size])
    voltage[magnitudes] = state[angles.size :] * np.exp(1j * np.angle(voltage[magnitudes]))
    return voltage


def _balance_residual(
    case: PowerFlowCase,
    ybus: csc_matrix,
    state: np.ndarray,
    angles: np.ndarray,
    magnitudes: np.ndarray,
) -> np.ndarray:
    voltage = _voltage_from_state(case, state, angles, magnitudes, case.initial_voltage)
    calculated = calculate_power(ybus, voltage)
    specified = case.specified_power
    return np.concatenate(
        (
            (specified.real - calculated.real)[np.concatenate((case.pv_indices, case.pq_indices))],
            (specified.imag - calculated.imag)[case.pq_indices],
        )
    )


def _finite_difference_jacobian(
    function: Callable[[np.ndarray], np.ndarray],
    state: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    base = function(state)
    jacobian = np.empty((base.size, state.size))
    for column in range(state.size):
        step = 1.0e-6 * max(1.0, abs(state[column]))
        plus = state.copy()
        minus = state.copy()
        plus[column] = min(upper[column] - _EPSILON, state[column] + step)
        minus[column] = max(lower[column] + _EPSILON, state[column] - step)
        denominator = plus[column] - minus[column]
        jacobian[:, column] = (function(plus) - function(minus)) / denominator
    return jacobian


def _balance_metrics(case: PowerFlowCase, residual: np.ndarray) -> tuple[float, float]:
    active_count = len(case.pv_indices) + len(case.pq_indices)
    return (
        float(np.max(np.abs(residual[:active_count]), initial=0.0)),
        float(np.max(np.abs(residual[active_count:]), initial=0.0)),
    )


def _interior_step(
    state: np.ndarray,
    direction: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    safety_factor: float,
) -> float:
    step = 1.0
    negative = direction < 0.0
    positive = direction > 0.0
    if np.any(negative):
        step = min(step, float(np.min((lower[negative] - state[negative]) / direction[negative])))
    if np.any(positive):
        step = min(step, float(np.min((upper[positive] - state[positive]) / direction[positive])))
    return min(1.0, max(0.0, safety_factor * step))


def _positive_step(values: np.ndarray, direction: np.ndarray, safety_factor: float) -> float:
    negative = direction < 0.0
    if not np.any(negative):
        return 1.0
    step = float(np.min(-values[negative] / direction[negative]))
    return min(1.0, max(0.0, safety_factor * step))


def _trust_step(direction: np.ndarray, maximum_step: float) -> float:
    maximum_direction = float(np.max(np.abs(direction), initial=0.0))
    if maximum_direction <= maximum_step:
        return 1.0
    return maximum_step / maximum_direction


def _project_interior(state: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    margin = np.minimum(_INTERIOR_MARGIN, (upper - lower) * 0.25)
    return np.minimum(np.maximum(state, lower + margin), upper - margin)


def _accept_state_step(
    case: PowerFlowCase,
    ybus: csc_matrix,
    state: np.ndarray,
    direction: np.ndarray,
    step: float,
    equality: np.ndarray,
    jacobian: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    angles: np.ndarray,
    magnitudes: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Backtrack the state step until the AC balance residual decreases."""
    current_norm = float(np.max(np.abs(equality), initial=0.0))
    for _ in range(12):
        candidate = _project_interior(state + step * direction, lower, upper)
        candidate_residual = _balance_residual(case, ybus, candidate, angles, magnitudes)
        candidate_norm = float(np.max(np.abs(candidate_residual), initial=0.0))
        if np.isfinite(candidate_norm) and candidate_norm < current_norm:
            return step, candidate
        step *= 0.5

    correction = np.linalg.lstsq(jacobian, -equality, rcond=None)[0]
    step = min(
        _interior_step(state, correction, lower, upper, 0.5),
        _trust_step(correction, _MAX_STATE_STEP),
    )
    for _ in range(12):
        candidate = _project_interior(state + step * correction, lower, upper)
        candidate_residual = _balance_residual(case, ybus, candidate, angles, magnitudes)
        candidate_norm = float(np.max(np.abs(candidate_residual), initial=0.0))
        if np.isfinite(candidate_norm) and candidate_norm < current_norm:
            return step, candidate
        step *= 0.5
    if np.all(np.isfinite(candidate)):
        return step, candidate
    return 0.0, state


def _emit(
    trace: list[IterationPowerFlowResult],
    iteration: int,
    max_dp: float,
    max_dq: float,
    max_residual: float,
    max_step: float,
    callback: Callable[[IterationPowerFlowResult], None] | None,
) -> None:
    item = IterationPowerFlowResult(
        iteration=iteration,
        max_dp=max_dp,
        max_dq=max_dq,
        max_control_residual=0.0,
        max_residual=max_residual,
        max_step=max_step,
    )
    trace.append(item)
    if callback is not None:
        callback(item)
