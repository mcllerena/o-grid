#include <algorithm>
#include <cmath>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "headers/case_data.h"
#include "headers/models/csc.h"
#include "headers/models/lcc.h"
#include "headers/models/ltc.h"
#include "headers/models/shunt.h"
#include "headers/models/svc.h"
#include "headers/utils/branch_flow.h"
#include "headers/utils/excel_export.h"
#include "headers/utils/linear_solver.h"
#include "headers/utils/network_reduction.h"
#include "headers/utils/newton_solver_api.h"
#include "headers/utils/reporting.h"
#include "headers/utils/ybus.h"

namespace {

struct LtcState {
    int ltc_index = -1;
    int from_index = -1;
    int to_index = -1;
    int control_index = -1;
};

struct LtcTapDerivative {
    double dp_from = 0.0;
    double dq_from = 0.0;
    double dp_to = 0.0;
    double dq_to = 0.0;
};

void append_power_flow_result(PowerFlowResult& result,
                              const PowerFlowResult& next_result,
                              std::ostream* live_trace_output) {
    const int iteration_offset = result.iterations;
    std::vector<IterationTrace> appended_trace;
    for (IterationTrace trace : next_result.trace) {
        if (trace.iteration == 0 && next_result.iterations > 0) {
            continue;
        }
        trace.iteration += iteration_offset;
        appended_trace.push_back(trace);
        if (live_trace_output != nullptr) {
            write_convergence_trace_row(*live_trace_output, trace);
        }
    }
    if (live_trace_output != nullptr && !appended_trace.empty()) {
        live_trace_output->flush();
    }

    PowerFlowResult merged_result = next_result;
    merged_result.iterations = result.iterations + next_result.iterations;
    merged_result.trace = result.trace;
    merged_result.trace.insert(merged_result.trace.end(), appended_trace.begin(), appended_trace.end());
    result = std::move(merged_result);
}

void write_trace_restart(std::ostream* live_trace_output, const std::string& reason) {
    if (live_trace_output == nullptr) {
        return;
    }
    *live_trace_output << "---- " << reason << " ----\n";
    live_trace_output->flush();
}

std::vector<int> collect_active_pq_buses(const std::vector<bool>& active_pq) {
    std::vector<int> pq_buses;
    for (std::size_t i = 0; i < active_pq.size(); ++i) {
        if (active_pq[i]) {
            pq_buses.push_back(static_cast<int>(i));
        }
    }
    return pq_buses;
}

void assign_vm_columns(std::vector<int>& vm_col, std::size_t n_angle, const std::vector<int>& pq_buses) {
    std::fill(vm_col.begin(), vm_col.end(), -1);
    for (std::size_t i = 0; i < pq_buses.size(); ++i) {
        vm_col[static_cast<std::size_t>(pq_buses[i])] = static_cast<int>(n_angle + i);
    }
}

double max_q_mismatch_for_pq_buses(const std::vector<int>& pq_buses,
                                   const std::vector<double>& q_spec,
                                   const std::vector<double>& svc_q_by_bus,
                                   const std::vector<double>& q_calc) {
    double max_q_mismatch = 0.0;
    for (int bus_index : pq_buses) {
        max_q_mismatch = std::max(max_q_mismatch, std::abs(q_spec[static_cast<std::size_t>(bus_index)] +
            svc_q_by_bus[static_cast<std::size_t>(bus_index)] - q_calc[static_cast<std::size_t>(bus_index)]));
    }
    return max_q_mismatch;
}

bool apply_pq_voltage_limit_control(const CaseData& data,
                                    std::vector<double>& vm,
                                    std::vector<bool>& active_pq,
                                    std::vector<int>& vlim_controlled,
                                    double max_q_mismatch,
                                    std::ostream* live_trace_output) {
    if (!data.vlim_enabled || max_q_mismatch >= data.vlim_reactive_start_tolerance) {
        return false;
    }

    int changed = 0;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        if (!active_pq[i] || data.buses[i].vmax <= data.buses[i].vmin) {
            continue;
        }
        if (vm[i] > data.buses[i].vmax + data.vlim_control_tolerance) {
            vm[i] = data.buses[i].vmax;
            active_pq[i] = false;
            vlim_controlled[i] = 1;
            ++changed;
        } else if (vm[i] < data.buses[i].vmin - data.vlim_control_tolerance) {
            vm[i] = data.buses[i].vmin;
            active_pq[i] = false;
            vlim_controlled[i] = 1;
            ++changed;
        }
    }

    if (changed > 0 && live_trace_output != nullptr) {
        *live_trace_output << "---- VLIM converted " << changed << " PQ bus(es) to fixed-voltage PV at violated limits ----\n";
        live_trace_output->flush();
    }
    return changed > 0;
}

bool apply_pv_reactive_limit_control(const CaseData& data,
                                     const std::vector<double>& q_calc,
                                     const std::vector<double>& svc_q_by_bus,
                                     std::vector<double>& q_spec,
                                     std::vector<bool>& active_pq,
                                     std::ostream* live_trace_output) {
    if (!data.bus_switching_enabled) {
        return false;
    }

    int changed = 0;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        const Bus& bus = data.buses[i];
        if (active_pq[i] || bus.type == BusType::Slack || !bus.switchable_pv_to_pq || !bus.has_q_limits) {
            continue;
        }
        const double required_q_mvar = (q_calc[i] - svc_q_by_bus[i]) * data.base_mva + bus.ql_mvar;
        if (required_q_mvar > bus.qmax_mvar + data.reactive_limit_tolerance_mvar) {
            q_spec[i] = (bus.qmax_mvar - bus.ql_mvar) / data.base_mva;
            active_pq[i] = true;
            ++changed;
        } else if (required_q_mvar < bus.qmin_mvar - data.reactive_limit_tolerance_mvar) {
            q_spec[i] = (bus.qmin_mvar - bus.ql_mvar) / data.base_mva;
            active_pq[i] = true;
            ++changed;
        }
    }

    if (changed > 0 && live_trace_output != nullptr) {
        *live_trace_output << "---- QLIM converted " << changed << " PV bus(es) to fixed-Q PQ at reactive limits ----\n";
        live_trace_output->flush();
    }
    return changed > 0;
}

double active_power_tolerance_pu(const CaseData& data) {
    return std::max(TOLERANCE, std::abs(data.ac_tepa_mw));
}

double reactive_power_tolerance_pu(const CaseData& data) {
    return std::max(TOLERANCE, std::abs(data.ac_tepr_mvar));
}

bool ac_solution_converged(const CaseData& data, const IterationTrace& trace) {
    return trace.max_dp <= active_power_tolerance_pu(data) &&
        trace.max_dq <= reactive_power_tolerance_pu(data) &&
        trace.max_control_residual <= data.vlim_control_tolerance;
}

std::complex<double> branch_y_entry_for_tap(const Branch& branch, bool from_row, bool from_col, double tap_value) {
    const std::complex<double> z(branch.r, branch.x);
    if (std::abs(z) <= TOLERANCE || tap_value <= TOLERANCE) {
        return std::complex<double>(0.0, 0.0);
    }
    const std::complex<double> y = 1.0 / z;
    const std::complex<double> charging(0.0, branch.b / 2.0);
    const std::complex<double> tap = std::polar(tap_value, branch.phase_rad);
    if (from_row && from_col) {
        return (y + charging) / (tap * std::conj(tap));
    }
    if (!from_row && !from_col) {
        return y + charging;
    }
    if (from_row && !from_col) {
        return -y / std::conj(tap);
    }
    return -y / tap;
}

void branch_power_at_tap(const Branch& branch,
                         int from_index,
                         int to_index,
                         const std::vector<double>& vm,
                         const std::vector<double>& va,
                         double tap_value,
                         double& p_from,
                         double& q_from,
                         double& p_to,
                         double& q_to) {
    const std::complex<double> yff = branch_y_entry_for_tap(branch, true, true, tap_value);
    const std::complex<double> yft = branch_y_entry_for_tap(branch, true, false, tap_value);
    const std::complex<double> ytf = branch_y_entry_for_tap(branch, false, true, tap_value);
    const std::complex<double> ytt = branch_y_entry_for_tap(branch, false, false, tap_value);
    const double vf = vm[static_cast<std::size_t>(from_index)];
    const double vt = vm[static_cast<std::size_t>(to_index)];
    const double aff = 0.0;
    const double aft = va[static_cast<std::size_t>(from_index)] - va[static_cast<std::size_t>(to_index)];
    const double atf = va[static_cast<std::size_t>(to_index)] - va[static_cast<std::size_t>(from_index)];
    p_from = vf * vf * yff.real() + vf * vt * (yft.real() * std::cos(aft) + yft.imag() * std::sin(aft));
    q_from = vf * vf * (yff.real() * std::sin(aff) - yff.imag() * std::cos(aff)) +
        vf * vt * (yft.real() * std::sin(aft) - yft.imag() * std::cos(aft));
    p_to = vt * vf * (ytf.real() * std::cos(atf) + ytf.imag() * std::sin(atf)) + vt * vt * ytt.real();
    q_to = vt * vf * (ytf.real() * std::sin(atf) - ytf.imag() * std::cos(atf)) - vt * vt * ytt.imag();
}

LtcTapDerivative ltc_tap_derivative(const Branch& branch,
                                    int from_index,
                                    int to_index,
                                    const std::vector<double>& vm,
                                    const std::vector<double>& va) {
    const double step = std::max(1.0e-5, std::abs(branch.tap) * 1.0e-5);
    const double tap_low = std::max(TOLERANCE, branch.tap - step);
    const double tap_high = branch.tap + step;
    double pf_low = 0.0;
    double qf_low = 0.0;
    double pt_low = 0.0;
    double qt_low = 0.0;
    double pf_high = 0.0;
    double qf_high = 0.0;
    double pt_high = 0.0;
    double qt_high = 0.0;
    branch_power_at_tap(branch, from_index, to_index, vm, va, tap_low, pf_low, qf_low, pt_low, qt_low);
    branch_power_at_tap(branch, from_index, to_index, vm, va, tap_high, pf_high, qf_high, pt_high, qt_high);
    const double denominator = tap_high - tap_low;
    LtcTapDerivative derivative;
    derivative.dp_from = (pf_high - pf_low) / denominator;
    derivative.dq_from = (qf_high - qf_low) / denominator;
    derivative.dp_to = (pt_high - pt_low) / denominator;
    derivative.dq_to = (qt_high - qt_low) / denominator;
    return derivative;
}

bool voltage_diverged(const CaseData& data, const std::vector<double>& vm) {
    for (double value : vm) {
        if (value < data.voltage_divergence_min_pu || value > data.voltage_divergence_max_pu) {
            return true;
        }
    }
    return false;
}

std::set<int> dbsh_voltage_controlled_buses(const CaseData& data) {
    std::map<int, int> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = static_cast<int>(i);
    }

    std::set<int> controlled_buses;
    for (const BusShunt& shunt : data.bus_shunts) {
        if (shunt.control_mode != "F" || shunt.vmax <= shunt.vmin ||
            shunt.qmax_mvar <= shunt.qmin_mvar + DISPLAY_TOLERANCE) {
            continue;
        }
        const int controlled_bus = shunt.owner_bus != 0 ? shunt.owner_bus : (shunt.remote_bus != 0 ? shunt.remote_bus : shunt.bus);
        const auto it = bus_index.find(controlled_bus);
        if (it == bus_index.end()) {
            continue;
        }
        const Bus& bus = data.buses[static_cast<std::size_t>(it->second)];
        if (bus.type == BusType::PQ && bus.base_voltage_group == "C") {
            controlled_buses.insert(it->second);
        }
    }
    return controlled_buses;
}

double max_active_mismatch(const std::vector<int>& angle_buses,
                           const std::vector<double>& p_spec,
                           const std::vector<double>& p_calc) {
    double max_mismatch = 0.0;
    for (int bus_index : angle_buses) {
        max_mismatch = std::max(max_mismatch, std::abs(p_spec[static_cast<std::size_t>(bus_index)] -
            p_calc[static_cast<std::size_t>(bus_index)]));
    }
    return max_mismatch;
}

double active_mismatch_norm(const std::vector<int>& angle_buses,
                            const std::vector<double>& p_spec,
                            const std::vector<double>& p_calc) {
    double sum = 0.0;
    for (int bus_index : angle_buses) {
        const double mismatch = p_spec[static_cast<std::size_t>(bus_index)] - p_calc[static_cast<std::size_t>(bus_index)];
        sum += mismatch * mismatch;
    }
    return std::sqrt(sum);
}

void warm_start_sparse_angles(const SparseYbus& ybus,
                              const std::vector<int>& angle_buses,
                              const std::vector<int>& angle_col,
                              const std::vector<double>& vm,
                              std::vector<double>& va,
                              const std::vector<double>& p_spec) {
    if (angle_buses.empty()) {
        return;
    }

    std::vector<double> p_calc;
    std::vector<double> q_calc;
    for (int pass = 0; pass < 24; ++pass) {
        calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
        const double current_residual = max_active_mismatch(angle_buses, p_spec, p_calc);
        const double current_norm = active_mismatch_norm(angle_buses, p_spec, p_calc);
        if (current_residual <= 0.1) {
            break;
        }

        SparseRealMatrix jacobian;
        jacobian.size = static_cast<int>(angle_buses.size());
        jacobian.rows.resize(static_cast<std::size_t>(jacobian.size));
        std::vector<double> mismatch(static_cast<std::size_t>(jacobian.size));

        for (std::size_t row = 0; row < angle_buses.size(); ++row) {
            const int i = angle_buses[row];
            mismatch[row] = p_spec[static_cast<std::size_t>(i)] - p_calc[static_cast<std::size_t>(i)];
            for (const SparseComplexEntry& entry : ybus.rows[static_cast<std::size_t>(i)]) {
                const int j = entry.col;
                const int col = angle_col[static_cast<std::size_t>(j)];
                if (col < 0) {
                    continue;
                }
                const double g = entry.value.real();
                const double b = entry.value.imag();
                const double angle = va[static_cast<std::size_t>(i)] - va[static_cast<std::size_t>(j)];
                const double value = i == j
                    ? -q_calc[static_cast<std::size_t>(i)] - b * vm[static_cast<std::size_t>(i)] * vm[static_cast<std::size_t>(i)]
                    : vm[static_cast<std::size_t>(i)] * vm[static_cast<std::size_t>(j)] * (g * std::sin(angle) - b * std::cos(angle));
                jacobian.rows[row].push_back({col, value});
            }
        }

        std::vector<double> step;
        try {
            step = solve_sparse_lu(jacobian, mismatch);
        } catch (const std::exception&) {
            step = solve_bicgstab(jacobian, mismatch, SPARSE_FALLBACK_TOLERANCE, 2000);
        }

        bool accepted = false;
        double alpha = 1.0;
        for (int attempt = 0; attempt < 8; ++attempt) {
            std::vector<double> trial_va = va;
            for (std::size_t i = 0; i < angle_buses.size(); ++i) {
                trial_va[static_cast<std::size_t>(angle_buses[i])] += alpha * step[i];
            }
            std::vector<double> trial_p;
            std::vector<double> trial_q;
            calculate_power_sparse(ybus, vm, trial_va, trial_p, trial_q);
            if (active_mismatch_norm(angle_buses, p_spec, trial_p) < current_norm) {
                va = std::move(trial_va);
                accepted = true;
                break;
            }
            alpha *= 0.5;
        }
        if (!accepted) {
            break;
        }
    }
}

PowerFlowResult solve_power_flow(const CaseData& data,
                                 double tolerance,
                                 int max_iterations,
                                 std::ostream* live_trace_output = nullptr) {
    (void)tolerance;
    const auto ybus = build_ybus(data);
    const std::size_t n = data.buses.size();

    std::vector<double> vm(n);
    std::vector<double> va(n);
    std::vector<double> p_spec(n);
    std::vector<double> q_spec(n);
    std::vector<int> angle_buses;
    std::vector<bool> active_pq(n, false);
    std::vector<int> vlim_controlled(n, 0);
    std::vector<int> vm_col(n, -1);
    const std::set<int> dbsh_controlled_buses = dbsh_voltage_controlled_buses(data);

    for (std::size_t i = 0; i < n; ++i) {
        const Bus& bus = data.buses[i];
        vm[i] = bus.voltage;
        va[i] = bus.angle_rad;
        p_spec[i] = (bus.pg_mw - bus.pl_mw) / data.base_mva;
        q_spec[i] = (bus.qg_mvar - bus.ql_mvar) / data.base_mva;

        if (bus.type != BusType::Slack) {
            angle_buses.push_back(static_cast<int>(i));
        }
        if (bus.type == BusType::PQ && bus.base_voltage_group != "U" &&
            dbsh_controlled_buses.find(static_cast<int>(i)) == dbsh_controlled_buses.end()) {
            active_pq[i] = true;
        }
    }

    for (const Lcc& lcc : data.lccs) {
        for (std::size_t i = 0; i < data.buses.size(); ++i) {
            if (data.buses[i].id == lcc.rectifier_bus) {
                p_spec[i] -= lcc.p_rectifier_mw / data.base_mva;
                q_spec[i] -= lcc.q_rectifier_mvar / data.base_mva;
            } else if (data.buses[i].id == lcc.inverter_bus) {
                p_spec[i] += lcc.p_inverter_mw / data.base_mva;
                q_spec[i] -= lcc.q_inverter_mvar / data.base_mva;
            }
        }
    }

    const std::size_t n_angle = angle_buses.size();

    std::vector<SvcState> svcs = build_svc_states(data, vm);
    std::vector<int> active_svcs;
    for (std::size_t i = 0; i < svcs.size(); ++i) {
        if (svcs[i].active) {
            active_svcs.push_back(static_cast<int>(i));
        }
    }

    std::vector<double> p_calc;
    std::vector<double> q_calc;
    PowerFlowResult result;

    for (int iteration = 0; iteration <= max_iterations; ++iteration) {
        update_svc_limits(svcs, vm);
        const std::vector<double> svc_q_by_bus = svc_q_injection_by_bus(svcs, n);
        calculate_power(ybus, vm, va, p_calc, q_calc);

        apply_pv_reactive_limit_control(data, q_calc, svc_q_by_bus, q_spec, active_pq, live_trace_output);
        std::vector<int> pq_buses = collect_active_pq_buses(active_pq);
        if (apply_pq_voltage_limit_control(data, vm, active_pq, vlim_controlled,
                max_q_mismatch_for_pq_buses(pq_buses, q_spec, svc_q_by_bus, q_calc), live_trace_output)) {
            calculate_power(ybus, vm, va, p_calc, q_calc);
            pq_buses = collect_active_pq_buses(active_pq);
        }
        assign_vm_columns(vm_col, n_angle, pq_buses);
        const std::size_t svc_offset = n_angle + pq_buses.size();
        const std::size_t n_state = svc_offset + active_svcs.size();

        std::vector<double> mismatch(n_state);
        IterationTrace trace;
        trace.iteration = iteration;
        for (std::size_t row = 0; row < angle_buses.size(); ++row) {
            const int i = angle_buses[row];
            mismatch[row] = p_spec[i] - p_calc[i];
            trace.max_dp = std::max(trace.max_dp, std::abs(mismatch[row]));
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[row]));
        }
        for (std::size_t row = 0; row < pq_buses.size(); ++row) {
            const int i = pq_buses[row];
            mismatch[n_angle + row] = q_spec[i] + svc_q_by_bus[i] - q_calc[i];
            trace.max_dq = std::max(trace.max_dq, std::abs(mismatch[n_angle + row]));
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[n_angle + row]));
        }
        for (std::size_t row = 0; row < active_svcs.size(); ++row) {
            const SvcState& svc = svcs[active_svcs[row]];
            mismatch[svc_offset + row] = -svc.control_residual;
            trace.max_control_residual = std::max(trace.max_control_residual, std::abs(mismatch[svc_offset + row]));
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[svc_offset + row]));
        }

        result.trace.push_back(trace);

        result.iterations = iteration;
        result.max_mismatch = trace.max_residual;
        if (voltage_diverged(data, vm)) {
            result.diverged = true;
            break;
        }
        if (ac_solution_converged(data, trace)) {
            result.converged = true;
            break;
        }
        if (iteration == max_iterations) {
            break;
        }

        std::vector<std::vector<double>> jacobian(n_state, std::vector<double>(n_state, 0.0));

        for (std::size_t row = 0; row < angle_buses.size(); ++row) {
            const int i = angle_buses[row];
            for (std::size_t col = 0; col < angle_buses.size(); ++col) {
                const int j = angle_buses[col];
                if (i == j) {
                    jacobian[row][col] = -q_calc[i] - ybus[i][i].imag() * vm[i] * vm[i];
                } else {
                    const double g = ybus[i][j].real();
                    const double b = ybus[i][j].imag();
                    const double angle = va[i] - va[j];
                    jacobian[row][col] = vm[i] * vm[j] * (g * std::sin(angle) - b * std::cos(angle));
                }
            }

            for (std::size_t col = 0; col < pq_buses.size(); ++col) {
                const int j = pq_buses[col];
                if (i == j) {
                    jacobian[row][n_angle + col] = p_calc[i] / vm[i] + ybus[i][i].real() * vm[i];
                } else {
                    const double g = ybus[i][j].real();
                    const double b = ybus[i][j].imag();
                    const double angle = va[i] - va[j];
                    jacobian[row][n_angle + col] = vm[i] * (g * std::cos(angle) + b * std::sin(angle));
                }
            }
        }

        for (std::size_t row = 0; row < pq_buses.size(); ++row) {
            const int i = pq_buses[row];
            for (std::size_t col = 0; col < angle_buses.size(); ++col) {
                const int j = angle_buses[col];
                if (i == j) {
                    jacobian[n_angle + row][col] = p_calc[i] - ybus[i][i].real() * vm[i] * vm[i];
                } else {
                    const double g = ybus[i][j].real();
                    const double b = ybus[i][j].imag();
                    const double angle = va[i] - va[j];
                    jacobian[n_angle + row][col] = -vm[i] * vm[j] * (g * std::cos(angle) + b * std::sin(angle));
                }
            }

            for (std::size_t col = 0; col < pq_buses.size(); ++col) {
                const int j = pq_buses[col];
                if (i == j) {
                    jacobian[n_angle + row][n_angle + col] = q_calc[i] / vm[i] - ybus[i][i].imag() * vm[i];
                } else {
                    const double g = ybus[i][j].real();
                    const double b = ybus[i][j].imag();
                    const double angle = va[i] - va[j];
                    jacobian[n_angle + row][n_angle + col] = vm[i] * (g * std::sin(angle) - b * std::cos(angle));
                }
            }
        }

        for (std::size_t col = 0; col < active_svcs.size(); ++col) {
            const SvcState& svc = svcs[active_svcs[col]];
            const int q_row = vm_col[svc.bus_index];
            if (q_row >= 0) {
                jacobian[q_row][svc_offset + col] = -1.0;
            }

            const std::size_t control_row = svc_offset + col;
            const int control_vm_col = vm_col[svc.control_bus_index];
            if (control_vm_col >= 0) {
                jacobian[control_row][control_vm_col] += svc_control_derivative_voltage(svc, svc.control_bus_index, vm);
            }
            const int comp_vm_col = vm_col[svc.bus_index];
            if (comp_vm_col >= 0 && comp_vm_col != control_vm_col) {
                jacobian[control_row][comp_vm_col] += svc_control_derivative_voltage(svc, svc.bus_index, vm);
            } else if (comp_vm_col >= 0) {
                jacobian[control_row][comp_vm_col] += svc_control_derivative_voltage(svc, svc.bus_index, vm);
            }
            jacobian[control_row][svc_offset + col] = svc_control_derivative_q(svc, vm);
        }

        const std::vector<double> step = solve_linear_system(jacobian, mismatch);
        double alpha = 1.0;
        std::vector<double> trial_vm = vm;
        std::vector<double> trial_va = va;
        std::vector<SvcState> trial_svcs = svcs;
        std::vector<double> trial_p;
        std::vector<double> trial_q;
        double trial_residual = std::numeric_limits<double>::infinity();

        for (int attempt = 0; attempt < 12; ++attempt) {
            trial_vm = vm;
            trial_va = va;
            trial_svcs = svcs;
            for (std::size_t i = 0; i < angle_buses.size(); ++i) {
                trial_va[angle_buses[i]] += alpha * step[i];
            }
            bool voltage_ok = true;
            for (std::size_t i = 0; i < pq_buses.size(); ++i) {
                const int bus_index = pq_buses[i];
                trial_vm[bus_index] += alpha * step[n_angle + i];
                const double lower_guard = std::max(data.voltage_divergence_min_pu, std::max(0.5, data.buses[bus_index].vmin * 0.8));
                const double upper_guard = std::max(data.voltage_divergence_max_pu, data.buses[bus_index].vmax * 1.5);
                if (trial_vm[bus_index] <= lower_guard || trial_vm[bus_index] >= upper_guard) {
                    voltage_ok = false;
                }
            }
            for (std::size_t i = 0; i < active_svcs.size(); ++i) {
                trial_svcs[active_svcs[i]].q_pu += alpha * step[svc_offset + i];
            }
            update_svc_limits(trial_svcs, trial_vm);

            calculate_power(ybus, trial_vm, trial_va, trial_p, trial_q);
            const std::vector<double> trial_svc_q_by_bus = svc_q_injection_by_bus(trial_svcs, n);
            trial_residual = 0.0;
            for (int bus_index : angle_buses) {
                trial_residual = std::max(trial_residual, std::abs(p_spec[bus_index] - trial_p[bus_index]));
            }
            for (int bus_index : pq_buses) {
                trial_residual = std::max(trial_residual, std::abs(q_spec[bus_index] + trial_svc_q_by_bus[bus_index] - trial_q[bus_index]));
            }
            for (int svc_index : active_svcs) {
                trial_residual = std::max(trial_residual, std::abs(trial_svcs[svc_index].control_residual));
            }

            if (voltage_ok && (trial_residual <= trace.max_residual || alpha < LINE_SEARCH_MIN_ALPHA)) {
                break;
            }
            alpha *= 0.5;
        }

        for (double value : step) {
            result.trace.back().max_step = std::max(result.trace.back().max_step, std::abs(alpha * value));
        }
        if (live_trace_output != nullptr) {
            write_convergence_trace_row(*live_trace_output, result.trace.back());
            live_trace_output->flush();
        }
        va = trial_va;
        vm = trial_vm;
        svcs = trial_svcs;
    }

    update_svc_limits(svcs, vm);
    calculate_power(ybus, vm, va, p_calc, q_calc);
    if (!result.trace.empty() && live_trace_output != nullptr && result.trace.back().max_step == 0.0) {
        write_convergence_trace_row(*live_trace_output, result.trace.back());
        live_trace_output->flush();
    }
    result.vm = vm;
    result.va = va;
    result.p_calc = p_calc;
    result.q_calc = q_calc;
    result.vlim_controlled = vlim_controlled;
    result.svc_q_mvar.resize(svcs.size());
    result.svc_q_initial_mvar.resize(svcs.size());
    result.svc_v_control_pu.resize(svcs.size());
    result.svc_v_ref_pu.resize(svcs.size());
    result.svc_active.resize(svcs.size());
    result.svc_state.resize(svcs.size());
    result.svc_control_residual.resize(svcs.size());
    for (std::size_t i = 0; i < svcs.size(); ++i) {
        const int control_index = svcs[i].control_bus_index;
        const double controlled_bus_q_mvar = q_calc[control_index] * data.base_mva + data.buses[control_index].ql_mvar;
        result.svc_q_mvar[i] = svcs[i].active ? svcs[i].q_pu * data.base_mva : controlled_bus_q_mvar;
        result.svc_q_initial_mvar[i] = svcs[i].q_initial_pu * data.base_mva;
        result.svc_v_control_pu[i] = vm[control_index];
        result.svc_v_ref_pu[i] = svcs[i].v_ref;
        result.svc_active[i] = svcs[i].active ? 1 : 0;
        result.svc_state[i] = svcs[i].limit_state;
        result.svc_control_residual[i] = svcs[i].control_residual;
    }
    return result;
}

PowerFlowResult solve_power_flow_sparse(CaseData& data,
                                        double tolerance,
                                        int max_iterations,
                                        std::ostream* live_trace_output = nullptr) {
    SparseYbus ybus = build_sparse_ybus(data);
    const std::size_t n = data.buses.size();

    std::vector<double> vm(n);
    std::vector<double> va(n);
    std::vector<double> p_spec(n);
    std::vector<double> q_spec(n);
    std::vector<int> angle_buses;
    std::vector<bool> active_pq(n, false);
    std::vector<int> vlim_controlled(n, 0);
    std::vector<int> angle_col(n, -1);
    std::vector<int> vm_col(n, -1);
    std::vector<int> q_row_by_bus(n, -1);
    std::map<int, int> bus_index;
    for (std::size_t i = 0; i < n; ++i) {
        bus_index[data.buses[i].id] = static_cast<int>(i);
    }
    const std::set<int> dbsh_controlled_buses = dbsh_voltage_controlled_buses(data);

    for (std::size_t i = 0; i < n; ++i) {
        const Bus& bus = data.buses[i];
        vm[i] = bus.voltage;
        va[i] = bus.angle_rad;
        p_spec[i] = (bus.pg_mw - bus.pl_mw) / data.base_mva;
        q_spec[i] = (bus.qg_mvar - bus.ql_mvar) / data.base_mva;

        if (bus.type != BusType::Slack) {
            angle_col[i] = static_cast<int>(angle_buses.size());
            angle_buses.push_back(static_cast<int>(i));
        }
        if (bus.type == BusType::PQ && bus.base_voltage_group != "U" &&
            dbsh_controlled_buses.find(static_cast<int>(i)) == dbsh_controlled_buses.end()) {
            active_pq[i] = true;
        }
    }

    for (const Lcc& lcc : data.lccs) {
        for (std::size_t i = 0; i < data.buses.size(); ++i) {
            if (data.buses[i].id == lcc.rectifier_bus) {
                p_spec[i] -= lcc.p_rectifier_mw / data.base_mva;
                q_spec[i] -= lcc.q_rectifier_mvar / data.base_mva;
            } else if (data.buses[i].id == lcc.inverter_bus) {
                p_spec[i] += lcc.p_inverter_mw / data.base_mva;
                q_spec[i] -= lcc.q_inverter_mvar / data.base_mva;
            }
        }
    }

    const int n_angle = static_cast<int>(angle_buses.size());
    warm_start_sparse_angles(ybus, angle_buses, angle_col, vm, va, p_spec);

    std::vector<SvcState> svcs = build_svc_states(data, vm);
    std::vector<int> active_svcs;
    for (std::size_t i = 0; i < svcs.size(); ++i) {
        if (svcs[i].active) {
            active_svcs.push_back(static_cast<int>(i));
        }
    }

    std::vector<double> p_calc;
    std::vector<double> q_calc;
    PowerFlowResult result;

    for (int iteration = 0; iteration <= max_iterations; ++iteration) {
        update_svc_limits(svcs, vm);
        const std::vector<double> svc_q_by_bus = svc_q_injection_by_bus(svcs, n);
        calculate_power_sparse(ybus, vm, va, p_calc, q_calc);

        std::vector<int> pq_buses = collect_active_pq_buses(active_pq);
        if (apply_pq_voltage_limit_control(data, vm, active_pq, vlim_controlled,
                max_q_mismatch_for_pq_buses(pq_buses, q_spec, svc_q_by_bus, q_calc), live_trace_output)) {
            calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
            pq_buses = collect_active_pq_buses(active_pq);
        }
        std::set<int> ltc_controlled_bus_indices;
        std::vector<LtcState> active_ltcs;
        active_ltcs.reserve(data.ltcs.size());
        constexpr bool inner_ltc_tap_equations_enabled = false;
        for (std::size_t ltc_index = 0; inner_ltc_tap_equations_enabled && ltc_index < data.ltcs.size(); ++ltc_index) {
            const Ltc& ltc = data.ltcs[ltc_index];
            if (!ltc.voltage_control || ltc.branch_index < 0 || ltc.tap_min <= 0.0 || ltc.tap_max <= ltc.tap_min) {
                continue;
            }
            const auto from_it = bus_index.find(ltc.from);
            const auto to_it = bus_index.find(ltc.to);
            const auto control_it = bus_index.find(ltc.control_bus);
            if (from_it == bus_index.end() || to_it == bus_index.end() || control_it == bus_index.end()) {
                continue;
            }
            if (!active_pq[static_cast<std::size_t>(control_it->second)]) {
                continue;
            }
            const double voltage_error = ltc.v_target - vm[static_cast<std::size_t>(control_it->second)];
            if ((ltc.tap <= ltc.tap_min + MIN_DENOMINATOR && voltage_error < 0.0) ||
                (ltc.tap >= ltc.tap_max - MIN_DENOMINATOR && voltage_error > 0.0)) {
                continue;
            }
            if (!ltc_controlled_bus_indices.insert(control_it->second).second) {
                continue;
            }
            active_ltcs.push_back({static_cast<int>(ltc_index), from_it->second, to_it->second, control_it->second});
            vm[static_cast<std::size_t>(control_it->second)] = ltc.v_target;
        }
        if (!active_ltcs.empty()) {
            calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
        }
        std::vector<int> vm_buses;
        vm_buses.reserve(pq_buses.size());
        for (int pq_bus : pq_buses) {
            if (ltc_controlled_bus_indices.find(pq_bus) == ltc_controlled_bus_indices.end()) {
                vm_buses.push_back(pq_bus);
            }
        }
        std::fill(q_row_by_bus.begin(), q_row_by_bus.end(), -1);
        for (std::size_t row = 0; row < pq_buses.size(); ++row) {
            q_row_by_bus[static_cast<std::size_t>(pq_buses[row])] = n_angle + static_cast<int>(row);
        }
        assign_vm_columns(vm_col, static_cast<std::size_t>(n_angle), vm_buses);
        const int svc_row_offset = n_angle + static_cast<int>(pq_buses.size());
        const int svc_col_offset = n_angle + static_cast<int>(vm_buses.size());
        const int ltc_col_offset = svc_col_offset + static_cast<int>(active_svcs.size());
        const int n_state = svc_row_offset + static_cast<int>(active_svcs.size());

        std::vector<double> mismatch(n_state);
        IterationTrace trace;
        trace.iteration = iteration;
        int max_p_bus_index = -1;
        int max_q_bus_index = -1;
        int max_svc_index = -1;
        for (std::size_t row = 0; row < angle_buses.size(); ++row) {
            const int i = angle_buses[row];
            mismatch[row] = p_spec[i] - p_calc[i];
            if (std::abs(mismatch[row]) > trace.max_dp) {
                trace.max_dp = std::abs(mismatch[row]);
                max_p_bus_index = i;
            }
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[row]));
        }
        for (std::size_t row = 0; row < pq_buses.size(); ++row) {
            const int i = pq_buses[row];
            const int target_row = n_angle + static_cast<int>(row);
            mismatch[target_row] = q_spec[i] + svc_q_by_bus[i] - q_calc[i];
            if (std::abs(mismatch[target_row]) > trace.max_dq) {
                trace.max_dq = std::abs(mismatch[target_row]);
                max_q_bus_index = i;
            }
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[target_row]));
        }
        for (std::size_t row = 0; row < active_svcs.size(); ++row) {
            const SvcState& svc = svcs[active_svcs[row]];
            mismatch[svc_row_offset + static_cast<int>(row)] = -svc.control_residual;
            if (std::abs(mismatch[svc_row_offset + static_cast<int>(row)]) > trace.max_control_residual) {
                trace.max_control_residual = std::abs(mismatch[svc_row_offset + static_cast<int>(row)]);
                max_svc_index = active_svcs[row];
            }
            trace.max_residual = std::max(trace.max_residual, std::abs(mismatch[svc_row_offset + static_cast<int>(row)]));
        }
        result.trace.push_back(trace);
        result.iterations = iteration;
        result.max_mismatch = trace.max_residual;
        if (voltage_diverged(data, vm)) {
            result.diverged = true;
            if (live_trace_output != nullptr) {
                write_convergence_trace_row(*live_trace_output, result.trace.back());
                live_trace_output->flush();
            }
            break;
        }
        if (ac_solution_converged(data, trace)) {
            result.converged = true;
            if (live_trace_output != nullptr) {
                write_convergence_trace_row(*live_trace_output, result.trace.back());
                live_trace_output->flush();
            }
            break;
        }
        if (iteration == max_iterations) {
            if (live_trace_output != nullptr) {
                *live_trace_output << "Sparse solve reached iteration cap; worst residual locations:\n";
                if (max_p_bus_index >= 0) {
                    const Bus& bus = data.buses[static_cast<std::size_t>(max_p_bus_index)];
                    *live_trace_output << "    - max dP bus " << bus.id << " " << bus.name
                                       << ": " << std::scientific << trace.max_dp << " pu\n";
                }
                if (max_q_bus_index >= 0) {
                    const Bus& bus = data.buses[static_cast<std::size_t>(max_q_bus_index)];
                    *live_trace_output << "    - max dQ bus " << bus.id << " " << bus.name
                                       << ": " << std::scientific << trace.max_dq << " pu\n";
                }
                if (max_svc_index >= 0) {
                    const Svc& svc = data.svcs[static_cast<std::size_t>(max_svc_index)];
                    *live_trace_output << "    - max SVC residual at bus " << svc.bus
                                       << ": " << std::scientific << trace.max_control_residual << " pu\n";
                }
                live_trace_output->flush();
            }
            break;
        }

        SparseRealMatrix jacobian;
        jacobian.size = n_state;
        jacobian.rows.resize(n_state);

        for (std::size_t row = 0; row < angle_buses.size(); ++row) {
            const int i = angle_buses[row];
            for (const SparseComplexEntry& entry : ybus.rows[i]) {
                const int j = entry.col;
                const double g = entry.value.real();
                const double b = entry.value.imag();
                const double angle = va[i] - va[j];

                if (angle_col[j] >= 0) {
                    const double value = i == j
                        ? -q_calc[i] - b * vm[i] * vm[i]
                        : vm[i] * vm[j] * (g * std::sin(angle) - b * std::cos(angle));
                    jacobian.rows[row].push_back({angle_col[j], value});
                }
                if (vm_col[j] >= 0) {
                    const double value = i == j
                        ? p_calc[i] / vm[i] + g * vm[i]
                        : vm[i] * (g * std::cos(angle) + b * std::sin(angle));
                    jacobian.rows[row].push_back({vm_col[j], value});
                }
            }
        }

        for (std::size_t row = 0; row < pq_buses.size(); ++row) {
            const int i = pq_buses[row];
            const int target_row = n_angle + static_cast<int>(row);
            for (const SparseComplexEntry& entry : ybus.rows[i]) {
                const int j = entry.col;
                const double g = entry.value.real();
                const double b = entry.value.imag();
                const double angle = va[i] - va[j];

                if (angle_col[j] >= 0) {
                    const double value = i == j
                        ? p_calc[i] - g * vm[i] * vm[i]
                        : -vm[i] * vm[j] * (g * std::cos(angle) + b * std::sin(angle));
                    jacobian.rows[target_row].push_back({angle_col[j], value});
                }
                if (vm_col[j] >= 0) {
                    const double value = i == j
                        ? q_calc[i] / vm[i] - b * vm[i]
                        : vm[i] * (g * std::sin(angle) - b * std::cos(angle));
                    jacobian.rows[target_row].push_back({vm_col[j], value});
                }
            }
        }

        for (std::size_t col = 0; col < active_svcs.size(); ++col) {
            const SvcState& svc = svcs[active_svcs[col]];
            const int q_row = q_row_by_bus[static_cast<std::size_t>(svc.bus_index)];
            if (q_row >= 0) {
                jacobian.rows[q_row].push_back({svc_col_offset + static_cast<int>(col), -1.0});
            }

            const int control_row = svc_row_offset + static_cast<int>(col);
            const int control_vm_col = vm_col[svc.control_bus_index];
            if (control_vm_col >= 0) {
                jacobian.rows[control_row].push_back({control_vm_col, svc_control_derivative_voltage(svc, svc.control_bus_index, vm)});
            }
            const int comp_vm_col = vm_col[svc.bus_index];
            if (comp_vm_col >= 0) {
                jacobian.rows[control_row].push_back({comp_vm_col, svc_control_derivative_voltage(svc, svc.bus_index, vm)});
            }
            jacobian.rows[control_row].push_back({svc_col_offset + static_cast<int>(col), svc_control_derivative_q(svc, vm)});
        }

        for (std::size_t col = 0; col < active_ltcs.size(); ++col) {
            const LtcState& ltc_state = active_ltcs[col];
            const Ltc& ltc = data.ltcs[static_cast<std::size_t>(ltc_state.ltc_index)];
            const Branch& branch = data.branches[static_cast<std::size_t>(ltc.branch_index)];
            const int tap_col = ltc_col_offset + static_cast<int>(col);
            const LtcTapDerivative derivative = ltc_tap_derivative(branch, ltc_state.from_index, ltc_state.to_index, vm, va);
            const int from_angle_row = angle_col[static_cast<std::size_t>(ltc_state.from_index)];
            if (from_angle_row >= 0) {
                jacobian.rows[from_angle_row].push_back({tap_col, derivative.dp_from});
            }
            const int to_angle_row = angle_col[static_cast<std::size_t>(ltc_state.to_index)];
            if (to_angle_row >= 0) {
                jacobian.rows[to_angle_row].push_back({tap_col, derivative.dp_to});
            }
            const int from_q_row = q_row_by_bus[static_cast<std::size_t>(ltc_state.from_index)];
            if (from_q_row >= 0) {
                jacobian.rows[from_q_row].push_back({tap_col, derivative.dq_from});
            }
            const int to_q_row = q_row_by_bus[static_cast<std::size_t>(ltc_state.to_index)];
            if (to_q_row >= 0) {
                jacobian.rows[to_q_row].push_back({tap_col, derivative.dq_to});
            }
        }

        std::vector<double> step;
        try {
            step = solve_sparse_lu(jacobian, mismatch);
        } catch (const std::exception&) {
            step = solve_bicgstab(jacobian, mismatch, std::min(SPARSE_FALLBACK_TOLERANCE, tolerance * 0.1), 2000);
        }
        double alpha = 1.0;
        std::vector<double> trial_vm = vm;
        std::vector<double> trial_va = va;
        std::vector<SvcState> trial_svcs = svcs;
        std::vector<double> base_ltc_taps(data.ltcs.size(), 0.0);
        std::vector<double> trial_ltc_taps(data.ltcs.size(), 0.0);
        std::vector<double> trial_p;
        std::vector<double> trial_q;
        double trial_residual = std::numeric_limits<double>::infinity();

        for (std::size_t i = 0; i < data.ltcs.size(); ++i) {
            base_ltc_taps[i] = data.ltcs[i].tap;
        }

        for (int attempt = 0; attempt < 12; ++attempt) {
            trial_vm = vm;
            trial_va = va;
            trial_svcs = svcs;
            for (std::size_t i = 0; i < data.ltcs.size(); ++i) {
                trial_ltc_taps[i] = base_ltc_taps[i];
            }
            for (std::size_t i = 0; i < angle_buses.size(); ++i) {
                trial_va[angle_buses[i]] += alpha * step[i];
            }
            bool voltage_ok = true;
            for (std::size_t i = 0; i < vm_buses.size(); ++i) {
                const int bus_index = vm_buses[i];
                trial_vm[bus_index] += alpha * step[n_angle + i];
                const double lower_guard = std::max(data.voltage_divergence_min_pu, std::max(0.5, data.buses[bus_index].vmin * 0.8));
                const double upper_guard = std::max(data.voltage_divergence_max_pu, data.buses[bus_index].vmax * 1.5);
                if (trial_vm[bus_index] <= lower_guard || trial_vm[bus_index] >= upper_guard) {
                    voltage_ok = false;
                }
            }
            for (std::size_t i = 0; i < active_svcs.size(); ++i) {
                trial_svcs[active_svcs[i]].q_pu += alpha * step[svc_col_offset + static_cast<int>(i)];
            }
            for (std::size_t i = 0; i < active_ltcs.size(); ++i) {
                const LtcState& ltc_state = active_ltcs[i];
                const Ltc& ltc = data.ltcs[static_cast<std::size_t>(ltc_state.ltc_index)];
                trial_vm[static_cast<std::size_t>(ltc_state.control_index)] = ltc.v_target;
                const double raw_tap = base_ltc_taps[static_cast<std::size_t>(ltc_state.ltc_index)] + alpha * step[ltc_col_offset + static_cast<int>(i)];
                trial_ltc_taps[static_cast<std::size_t>(ltc_state.ltc_index)] =
                    std::max(ltc.tap_min, std::min(ltc.tap_max, raw_tap));
            }
            update_svc_limits(trial_svcs, trial_vm);
            const std::vector<double> trial_svc_q_by_bus = svc_q_injection_by_bus(trial_svcs, n);

            for (std::size_t i = 0; i < active_ltcs.size(); ++i) {
                const LtcState& ltc_state = active_ltcs[i];
                Ltc& ltc = data.ltcs[static_cast<std::size_t>(ltc_state.ltc_index)];
                ltc.tap = trial_ltc_taps[static_cast<std::size_t>(ltc_state.ltc_index)];
                data.branches[static_cast<std::size_t>(ltc.branch_index)].tap = ltc.tap;
            }
            const SparseYbus trial_ybus = build_sparse_ybus(data);
            calculate_power_sparse(trial_ybus, trial_vm, trial_va, trial_p, trial_q);
            trial_residual = 0.0;
            for (int bus_index : angle_buses) {
                trial_residual = std::max(trial_residual, std::abs(p_spec[bus_index] - trial_p[bus_index]));
            }
            for (int bus_index : pq_buses) {
                trial_residual = std::max(trial_residual, std::abs(q_spec[bus_index] + trial_svc_q_by_bus[bus_index] - trial_q[bus_index]));
            }
            for (int svc_index : active_svcs) {
                trial_residual = std::max(trial_residual, std::abs(trial_svcs[svc_index].control_residual));
            }
            if (voltage_ok && (trial_residual <= trace.max_residual || alpha < LINE_SEARCH_MIN_ALPHA)) {
                break;
            }
            alpha *= 0.5;
        }

        for (double value : step) {
            result.trace.back().max_step = std::max(result.trace.back().max_step, std::abs(alpha * value));
        }
        if (live_trace_output != nullptr) {
            write_convergence_trace_row(*live_trace_output, result.trace.back());
            live_trace_output->flush();
        }

        va = trial_va;
        vm = trial_vm;
        svcs = trial_svcs;
        for (std::size_t i = 0; i < active_ltcs.size(); ++i) {
            const LtcState& ltc_state = active_ltcs[i];
            Ltc& ltc = data.ltcs[static_cast<std::size_t>(ltc_state.ltc_index)];
            ltc.tap = trial_ltc_taps[static_cast<std::size_t>(ltc_state.ltc_index)];
            data.branches[static_cast<std::size_t>(ltc.branch_index)].tap = ltc.tap;
        }
        ybus = build_sparse_ybus(data);
    }

    update_svc_limits(svcs, vm);
    calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
    result.vm = vm;
    result.va = va;
    result.p_calc = p_calc;
    result.q_calc = q_calc;
    result.vlim_controlled = vlim_controlled;
    result.svc_q_mvar.resize(svcs.size());
    result.svc_q_initial_mvar.resize(svcs.size());
    result.svc_v_control_pu.resize(svcs.size());
    result.svc_v_ref_pu.resize(svcs.size());
    result.svc_active.resize(svcs.size());
    result.svc_state.resize(svcs.size());
    result.svc_control_residual.resize(svcs.size());
    for (std::size_t i = 0; i < svcs.size(); ++i) {
        const int control_index = svcs[i].control_bus_index;
        const double controlled_bus_q_mvar = q_calc[control_index] * data.base_mva + data.buses[control_index].ql_mvar;
        result.svc_q_mvar[i] = svcs[i].active ? svcs[i].q_pu * data.base_mva : controlled_bus_q_mvar;
        result.svc_q_initial_mvar[i] = svcs[i].q_initial_pu * data.base_mva;
        result.svc_v_control_pu[i] = vm[control_index];
        result.svc_v_ref_pu[i] = svcs[i].v_ref;
        result.svc_active[i] = svcs[i].active ? 1 : 0;
        result.svc_state[i] = svcs[i].limit_state;
        result.svc_control_residual[i] = svcs[i].control_residual;
    }
    return result;
}

bool use_sparse_power_flow(const CaseData& data) {
    return data.buses.size() >= 1000;
}

void seed_next_solve_from_result(CaseData& data, const PowerFlowResult& result) {
    for (std::size_t i = 0; i < data.buses.size() && i < result.vm.size() && i < result.va.size(); ++i) {
        data.buses[i].voltage = result.vm[i];
        data.buses[i].angle_rad = result.va[i];
    }
}

PowerFlowResult solve_power_flow_auto(CaseData& data,
                                      double tolerance,
                                      int max_iterations,
                                      std::ostream* live_trace_output = nullptr) {
    if (use_sparse_power_flow(data)) {
        return solve_power_flow_sparse(data, tolerance, max_iterations, live_trace_output);
    }
    if (!data.svcs.empty() || !data.cscs.empty() || !data.ltcs.empty() || !data.psts.empty() || !data.lccs.empty()) {
        return solve_power_flow(data, tolerance, max_iterations, live_trace_output);
    }
    return solve_power_flow(data, tolerance, max_iterations, live_trace_output);
}

PowerFlowResult solve_power_flow_with_sequential_lcc(CaseData& data,
                                                     double tolerance,
                                                     int max_iterations,
                                                     std::ostream* live_trace_output = nullptr) {
    PowerFlowResult result = solve_power_flow_auto(data, tolerance, max_iterations, live_trace_output);
    if (data.lccs.empty() || !result.converged) {
        return result;
    }

    constexpr int max_lcc_passes = 12;
    constexpr double damping = 1.0;
    bool interface_converged = false;
    bool rejected_lcc_trial = false;
    for (int pass = 0; pass < max_lcc_passes; ++pass) {
        seed_next_solve_from_result(data, result);
        const CaseData accepted_data = data;
        const LccInterfaceDeviation deviation = update_lcc_from_dc_solution(data, result, damping);
        if (deviation.max_active_mw <= data.lcc_tepa_mw &&
            deviation.max_reactive_mvar <= data.lcc_tepr_mvar) {
            interface_converged = true;
            break;
        }

        write_trace_restart(live_trace_output,
                            "LCC outer pass " + std::to_string(pass + 1) + " updated converter interface injections; re-solving AC equations");
        const PowerFlowResult next_result = solve_power_flow_auto(data, tolerance, max_iterations, nullptr);
        if (!next_result.converged) {
            data = accepted_data;
            rejected_lcc_trial = true;
            write_trace_restart(live_trace_output,
                                "LCC outer pass " + std::to_string(pass + 1) + " rejected; retaining last converged AC solution");
            break;
        }
        append_power_flow_result(result, next_result, live_trace_output);
    }
    if (!interface_converged && !rejected_lcc_trial) {
        result.converged = false;
    }
    return result;
}

PowerFlowResult solve_power_flow_with_outer_controls(CaseData& data,
                                                     double tolerance,
                                                     int max_iterations,
                                                     std::ostream* live_trace_output = nullptr) {
    PowerFlowResult result = solve_power_flow_with_sequential_lcc(data, tolerance, max_iterations, live_trace_output);
    if (!result.converged && result.diverged) {
        return result;
    }

    constexpr int max_control_passes = 12;
    for (int pass = 0; pass < max_control_passes; ++pass) {
        const CaseData accepted_data = data;
        const bool shunts_changed = adjust_switched_bus_shunts(data, result);
        const bool taps_changed = adjust_ltc_taps(data, result);
        if (!shunts_changed && !taps_changed) {
            break;
        }

        seed_next_solve_from_result(data, result);
        write_trace_restart(live_trace_output,
                            "outer control pass " + std::to_string(pass + 1) + " changed shunts/taps; re-solving AC equations");
        const PowerFlowResult next_result = solve_power_flow_with_sequential_lcc(data, tolerance, max_iterations, nullptr);
        if (!next_result.converged) {
            if (!result.converged && !next_result.diverged && next_result.max_mismatch < result.max_mismatch) {
                append_power_flow_result(result, next_result, live_trace_output);
                continue;
            }
            data = accepted_data;
            break;
        }
        append_power_flow_result(result, next_result, live_trace_output);
    }
    return result;
}

[[maybe_unused]] std::set<int> parse_int_set(const std::string& text, const std::string& option_name) {
    std::set<int> values;
    std::stringstream stream(text);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (item.empty()) {
            continue;
        }
        values.insert(std::stoi(item));
    }
    if (values.empty()) {
        throw std::runtime_error(option_name + " requires at least one integer value");
    }
    return values;
}

[[maybe_unused]] std::set<std::string> parse_string_set(const std::string& text, const std::string& option_name) {
    std::set<std::string> values;
    std::stringstream stream(text);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (!item.empty()) {
            values.insert(item);
        }
    }
    if (values.empty()) {
        throw std::runtime_error(option_name + " requires at least one value");
    }
    return values;
}

[[maybe_unused]] std::string reduction_method_label(EquivalentReductionMethod method) {
    if (method == EquivalentReductionMethod::Ward) {
        return "Ward extended";
    }
    if (method == EquivalentReductionMethod::ConstantPowerInjection) {
        return "constant-power injection";
    }
    return "none";
}

} // namespace

PowerFlowResult solve_power_flow_newton_with_outer_controls(CaseData& data,
                                                            double tolerance,
                                                            int max_iterations,
                                                            std::ostream* live_trace_output) {
    return solve_power_flow_with_outer_controls(data, tolerance, max_iterations, live_trace_output);
}

#ifndef POWER_SIMULATOR_NEWTON_LIBRARY
int main(int argc, char** argv) {
    std::string case_path = "data/d_9nodes.dat";
    double tolerance = DEFAULT_POWER_FLOW_TOLERANCE;
    int max_iterations = 50;
    bool save_results = false;
    bool export_excel = false;
    std::string save_path;
    std::string excel_path;
    EquivalentReductionOptions reduction_options;
    bool bus_switching = false;
    std::string bus_switching_root;
    std::vector<std::string> positional_args;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--save") {
            save_results = true;
            if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) {
                save_path = argv[++i];
            }
        } else if (arg == "--to-excel") {
            export_excel = true;
            if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) {
                excel_path = argv[++i];
            }
        } else if (arg == "--ward" || arg == "--ward-reduction") {
            reduction_options.method = EquivalentReductionMethod::Ward;
        } else if (arg == "--injection") {
            reduction_options.method = EquivalentReductionMethod::ConstantPowerInjection;
        } else if (arg == "--bus-switching") {
            bus_switching = true;
            if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) {
                bus_switching_root = argv[++i];
            }
        } else if (arg == "--zmax") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--zmax requires a value");
            }
            reduction_options.zmax = std::stod(argv[++i]);
        } else if (arg == "--retain-buses") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--retain-buses requires a comma-separated list");
            }
            reduction_options.retained_buses = parse_int_set(argv[++i], arg);
        } else if (arg == "--external-buses") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--external-buses requires a comma-separated list");
            }
            reduction_options.external_buses = parse_int_set(argv[++i], arg);
        } else if (arg == "--retain-areas") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--retain-areas requires a comma-separated list");
            }
            reduction_options.retained_areas = parse_int_set(argv[++i], arg);
        } else if (arg == "--external-areas") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--external-areas requires a comma-separated list");
            }
            reduction_options.external_areas = parse_int_set(argv[++i], arg);
        } else if (arg == "--retain-groups") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--retain-groups requires a comma-separated list");
            }
            reduction_options.retained_voltage_groups = parse_string_set(argv[++i], arg);
        } else if (arg == "--external-groups") {
            if (i + 1 >= argc) {
                throw std::runtime_error("--external-groups requires a comma-separated list");
            }
            reduction_options.external_voltage_groups = parse_string_set(argv[++i], arg);
        } else {
            positional_args.push_back(arg);
        }
    }

    if (!positional_args.empty()) {
        case_path = positional_args[0];
    }
    if (positional_args.size() > 1) {
        tolerance = std::stod(positional_args[1]);
    }
    if (positional_args.size() > 2) {
        max_iterations = std::stoi(positional_args[2]);
    }
    if (save_results && save_path.empty()) {
        save_path = default_results_path(case_path);
    }

    try {
        CaseData data = read_case_file(case_path);
        BusSwitchingSummary bus_switching_summary;
        if (bus_switching) {
            bus_switching_summary = load_anarede_bus_switching(data, case_path, bus_switching_root);
        }
        const EquivalentReductionSummary reduction_summary = apply_equivalent_network_reduction(data, reduction_options);
        write_case_header(std::cout, case_path, data);
        if (bus_switching) {
            std::cout << "ANAREDE bus switching: loaded " << bus_switching_summary.pq_to_pv_candidates
                      << " PQ->PV candidates, " << bus_switching_summary.pv_to_pq_candidates
                      << " PV->PQ candidates, updated Q limits on " << bus_switching_summary.updated_q_limits
                      << " bus(es)\n";
        }
        if (reduction_options.method != EquivalentReductionMethod::None) {
            std::cout << "Network equivalent reduction:\n";
            if (reduction_summary.applied) {
                std::cout << "    - " << reduction_method_label(reduction_options.method) << " applied\n"
                          << "    - Retained buses: " << reduction_summary.retained_buses << "\n"
                          << "    - External buses eliminated: " << reduction_summary.external_buses << "\n"
                          << "    - Boundary buses: " << reduction_summary.boundary_buses << "\n"
                          << "    - Removed branches: " << reduction_summary.removed_branches << "\n"
                          << "    - Added branches: " << reduction_summary.added_branches << "\n"
                          << "    - Added shunts: " << reduction_summary.added_shunts << "\n";
            } else {
                std::cout << "    - " << reduction_method_label(reduction_options.method) << " requested\n"
                          << "    - No explicit external/retained selection was provided, so only the default zero-impedance reduction was applied\n";
            }
        }
        std::cout << "Estimated dense matrix memory: " << std::fixed << std::setprecision(2)
                  << estimate_dense_memory_gb(data) << " GB\n";
        if (use_sparse_power_flow(data)) {
            std::cout << "Solver mode: sparse Ybus/Jacobian with Brazilian device support\n";
        } else if (!data.svcs.empty() || !data.cscs.empty() || !data.ltcs.empty() || !data.psts.empty() || !data.lccs.empty()) {
            std::cout << "Solver mode: dense direct Newton solve with Brazilian device equations\n";
        } else {
            std::cout << "Solver mode: dense direct Newton solve\n";
        }
        std::cout << "AC convergence criteria: |dP| <= " << std::scientific << std::setprecision(4)
                  << active_power_tolerance_pu(data) << " pu (TEPA), |dQ| <= "
                  << reactive_power_tolerance_pu(data) << " pu (TEPR), controls <= "
                  << data.vlim_control_tolerance << " pu (TLVC)\n";
        std::cout << "AC divergence voltage window: [" << data.voltage_divergence_min_pu
              << ", " << data.voltage_divergence_max_pu << "] pu (VDVN/VDVM)\n";
        std::cout << "Near-zero guard tolerance: " << std::scientific << std::setprecision(4) << TOLERANCE << "\n";
        write_convergence_trace_header(std::cout);
        std::cout.flush();

        const PowerFlowResult result = solve_power_flow_with_outer_controls(data, tolerance, max_iterations, &std::cout);
        std::cout << std::string(62, '-') << "\n";
        std::cout << "Converged: " << (result.converged ? "yes" : "no") << "\n";
        std::cout << "Iterations: " << result.iterations << "\n";
        std::cout << "Max mismatch: " << std::scientific << result.max_mismatch << " pu\n";
        const std::vector<BranchFlow> branch_flows = calculate_branch_flows(data, result.vm, result.va);
        write_power_balance_summary(std::cout, data, result, branch_flows);
        write_violation_summary(std::cout, make_violation_summary(data, result, branch_flows));

        if (save_results) {
            std::ofstream output(save_path);
            if (!output) {
                throw std::runtime_error("Could not write results file: " + save_path);
            }
            write_full_report(output, case_path, data, result, branch_flows);
            std::cout << "\nSaved results to: " << save_path << "\n";
        }

        if (export_excel) {
            const std::string output_path = resolve_excel_results_path(case_path, excel_path, "nr");
            export_results_to_excel(case_path, data, result, branch_flows, excel_path, "nr");
            std::cout << "\nExported Excel results to: " << output_path << "\n";
        }

        return result.converged ? 0 : 2;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << "\n";
        return 1;
    }
}
#endif