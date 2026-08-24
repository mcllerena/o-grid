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

void assign_pq_columns(std::vector<int>& pq_col, const std::vector<int>& pq_buses) {
	std::fill(pq_col.begin(), pq_col.end(), -1);
	for (std::size_t i = 0; i < pq_buses.size(); ++i) {
		pq_col[static_cast<std::size_t>(pq_buses[i])] = static_cast<int>(i);
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

bool voltage_diverged(const CaseData& data, const std::vector<double>& vm) {
	for (double value : vm) {
		if (value < data.voltage_divergence_min_pu || value > data.voltage_divergence_max_pu) {
			return true;
		}
	}
	return false;
}

bool apply_pq_voltage_limit_control(const CaseData& data,
									std::vector<double>& vm,
									std::vector<bool>& active_pq,
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
			++changed;
		} else if (vm[i] < data.buses[i].vmin - data.vlim_control_tolerance) {
			vm[i] = data.buses[i].vmin;
			active_pq[i] = false;
			++changed;
		}
	}

	if (changed > 0 && live_trace_output != nullptr) {
		*live_trace_output << "---- VLIM converted " << changed << " PQ bus(es) to fixed-voltage PV at violated limits ----\n";
		live_trace_output->flush();
	}
	return changed > 0;
}

void build_power_spec(const CaseData& data, std::vector<double>& p_spec, std::vector<double>& q_spec) {
	p_spec.assign(data.buses.size(), 0.0);
	q_spec.assign(data.buses.size(), 0.0);
	for (std::size_t i = 0; i < data.buses.size(); ++i) {
		const Bus& bus = data.buses[i];
		p_spec[i] = (bus.pg_mw - bus.pl_mw) / data.base_mva;
		q_spec[i] = (bus.qg_mvar - bus.ql_mvar) / data.base_mva;
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
}

SparseRealMatrix make_decoupled_b_matrix(const SparseYbus& ybus,
										 const std::vector<int>& row_buses,
										 const std::vector<int>& col_by_bus) {
	SparseRealMatrix matrix;
	matrix.size = static_cast<int>(row_buses.size());
	matrix.rows.resize(row_buses.size());
	for (std::size_t row = 0; row < row_buses.size(); ++row) {
		const int bus_index = row_buses[row];
		for (const SparseComplexEntry& entry : ybus.rows[bus_index]) {
			const int col = col_by_bus[static_cast<std::size_t>(entry.col)];
			if (col >= 0) {
				matrix.rows[row].push_back({col, -entry.value.imag()});
			}
		}
	}
	return matrix;
}

void refresh_decoupled_svc_controls(std::vector<SvcState>& svcs, const std::vector<double>& vm) {
	for (SvcState& svc : svcs) {
		if (!svc.active || std::abs(svc.slope) <= TOLERANCE) {
			continue;
		}
		if (svc.mode == 1) {
			svc.q_pu = (svc.v_ref - vm[svc.control_bus_index]) * vm[svc.bus_index] / svc.slope;
		} else {
			svc.q_pu = (svc.v_ref - vm[svc.control_bus_index]) / svc.slope;
		}
	}
	update_svc_limits(svcs, vm);
}

std::vector<double> solve_constant_matrix(const SparseRealMatrix& matrix, const std::vector<double>& rhs, double tolerance) {
	if (matrix.size == 0) {
		return {};
	}
	try {
		return solve_sparse_lu(matrix, rhs);
	} catch (const std::exception&) {
		return solve_bicgstab(matrix, rhs, std::min(SPARSE_FALLBACK_TOLERANCE, tolerance * 0.1), 2000);
	}
}

void seed_next_solve_from_result(CaseData& data, const PowerFlowResult& result) {
	for (std::size_t i = 0; i < data.buses.size() && i < result.vm.size() && i < result.va.size(); ++i) {
		data.buses[i].voltage = result.vm[i];
		data.buses[i].angle_rad = result.va[i];
	}
}

PowerFlowResult solve_power_flow_fd_once(const CaseData& data,
										 double tolerance,
										 int max_iterations,
										 std::ostream* live_trace_output = nullptr) {
	const SparseYbus ybus = build_sparse_ybus(data);
	const std::size_t n = data.buses.size();

	std::vector<double> vm(n);
	std::vector<double> va(n);
	std::vector<double> p_spec;
	std::vector<double> q_spec;
	std::vector<int> angle_buses;
	std::vector<bool> active_pq(n, false);
	std::vector<int> angle_col(n, -1);
	std::vector<int> pq_col(n, -1);

	for (std::size_t i = 0; i < n; ++i) {
		vm[i] = data.buses[i].voltage;
		va[i] = data.buses[i].angle_rad;
		if (data.buses[i].type != BusType::Slack) {
			angle_col[i] = static_cast<int>(angle_buses.size());
			angle_buses.push_back(static_cast<int>(i));
		}
		if (data.buses[i].type == BusType::PQ) {
			active_pq[i] = true;
		}
	}

	build_power_spec(data, p_spec, q_spec);
	const SparseRealMatrix b_prime = make_decoupled_b_matrix(ybus, angle_buses, angle_col);
	std::vector<int> pq_buses = collect_active_pq_buses(active_pq);
	assign_pq_columns(pq_col, pq_buses);
	SparseRealMatrix b_double_prime = make_decoupled_b_matrix(ybus, pq_buses, pq_col);

	std::vector<SvcState> svcs = build_svc_states(data, vm);
	std::vector<double> p_calc;
	std::vector<double> q_calc;
	PowerFlowResult result;

	for (int iteration = 0; iteration <= max_iterations; ++iteration) {
		refresh_decoupled_svc_controls(svcs, vm);
		const std::vector<double> svc_q_by_bus = svc_q_injection_by_bus(svcs, n);
		calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
		if (apply_pq_voltage_limit_control(data, vm, active_pq,
				max_q_mismatch_for_pq_buses(pq_buses, q_spec, svc_q_by_bus, q_calc), live_trace_output)) {
			calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
			pq_buses = collect_active_pq_buses(active_pq);
			assign_pq_columns(pq_col, pq_buses);
			b_double_prime = make_decoupled_b_matrix(ybus, pq_buses, pq_col);
		}

		IterationTrace trace;
		trace.iteration = iteration;
		std::vector<double> rhs_p(angle_buses.size(), 0.0);
		std::vector<double> rhs_q(pq_buses.size(), 0.0);
		for (std::size_t row = 0; row < angle_buses.size(); ++row) {
			const int bus_index = angle_buses[row];
			const double mismatch = p_spec[bus_index] - p_calc[bus_index];
			rhs_p[row] = mismatch;
			trace.max_dp = std::max(trace.max_dp, std::abs(mismatch));
			trace.max_residual = std::max(trace.max_residual, std::abs(mismatch));
		}
		for (std::size_t row = 0; row < pq_buses.size(); ++row) {
			const int bus_index = pq_buses[row];
			const double mismatch = q_spec[bus_index] + svc_q_by_bus[bus_index] - q_calc[bus_index];
			rhs_q[row] = mismatch;
			trace.max_dq = std::max(trace.max_dq, std::abs(mismatch));
			trace.max_residual = std::max(trace.max_residual, std::abs(mismatch));
		}
		for (const SvcState& svc : svcs) {
			trace.max_control_residual = std::max(trace.max_control_residual, std::abs(svc.control_residual));
			trace.max_residual = std::max(trace.max_residual, std::abs(svc.control_residual));
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
			break;
		}

		const std::vector<double> d_angle = solve_constant_matrix(b_prime, rhs_p, tolerance);
		const std::vector<double> d_voltage = solve_constant_matrix(b_double_prime, rhs_q, tolerance);
		std::vector<double> limited_d_angle = d_angle;
		std::vector<double> limited_d_voltage = d_voltage;
		const double max_angle_step = 5.0 * kPi / 180.0;
		constexpr double max_voltage_step = 0.1;
		for (double& value : limited_d_angle) {
			value = std::max(-max_angle_step, std::min(max_angle_step, value));
		}
		for (std::size_t i = 0; i < limited_d_voltage.size(); ++i) {
			const double base_voltage = std::max(std::abs(vm[pq_buses[i]]), MIN_DENOMINATOR);
			const double limited_delta = std::max(-max_voltage_step, std::min(max_voltage_step, limited_d_voltage[i] * vm[pq_buses[i]]));
			limited_d_voltage[i] = limited_delta / base_voltage;
		}

		double alpha = 1.0;
		std::vector<double> trial_vm;
		std::vector<double> trial_va;
		std::vector<SvcState> trial_svcs;
		std::vector<double> trial_p;
		std::vector<double> trial_q;
		double trial_residual = std::numeric_limits<double>::infinity();
		for (int attempt = 0; attempt < 12; ++attempt) {
			trial_vm = vm;
			trial_va = va;
			trial_svcs = svcs;
			for (std::size_t i = 0; i < angle_buses.size(); ++i) {
				trial_va[angle_buses[i]] += alpha * limited_d_angle[i];
			}
			bool voltage_ok = true;
			for (std::size_t i = 0; i < pq_buses.size(); ++i) {
				const int bus_index = pq_buses[i];
				trial_vm[bus_index] += alpha * limited_d_voltage[i] * trial_vm[bus_index];
				const double lower_guard = std::max(data.voltage_divergence_min_pu, std::max(0.5, data.buses[bus_index].vmin * 0.8));
				const double upper_guard = std::max(data.voltage_divergence_max_pu, data.buses[bus_index].vmax * 1.5);
				if (trial_vm[bus_index] <= lower_guard || trial_vm[bus_index] >= upper_guard) {
					voltage_ok = false;
				}
			}
			refresh_decoupled_svc_controls(trial_svcs, trial_vm);
			const std::vector<double> trial_svc_q_by_bus = svc_q_injection_by_bus(trial_svcs, n);
			calculate_power_sparse(ybus, trial_vm, trial_va, trial_p, trial_q);
			trial_residual = 0.0;
			for (int bus_index : angle_buses) {
				trial_residual = std::max(trial_residual, std::abs(p_spec[bus_index] - trial_p[bus_index]));
			}
			for (int bus_index : pq_buses) {
				trial_residual = std::max(trial_residual, std::abs(q_spec[bus_index] + trial_svc_q_by_bus[bus_index] - trial_q[bus_index]));
			}
			for (const SvcState& svc : trial_svcs) {
				trial_residual = std::max(trial_residual, std::abs(svc.control_residual));
			}
			if (voltage_ok && (trial_residual <= trace.max_residual || alpha < LINE_SEARCH_MIN_ALPHA)) {
				break;
			}
			alpha *= 0.5;
		}

		for (double value : limited_d_angle) {
			result.trace.back().max_step = std::max(result.trace.back().max_step, std::abs(alpha * value));
		}
		for (std::size_t i = 0; i < limited_d_voltage.size(); ++i) {
			result.trace.back().max_step = std::max(result.trace.back().max_step,
				std::abs(alpha * limited_d_voltage[i] * vm[pq_buses[i]]));
		}
		if (live_trace_output != nullptr) {
			write_convergence_trace_row(*live_trace_output, result.trace.back());
			live_trace_output->flush();
		}
		vm = trial_vm;
		va = trial_va;
		svcs = trial_svcs;
	}

	refresh_decoupled_svc_controls(svcs, vm);
	calculate_power_sparse(ybus, vm, va, p_calc, q_calc);
	result.vm = vm;
	result.va = va;
	result.p_calc = p_calc;
	result.q_calc = q_calc;
	result.svc_q_mvar.resize(svcs.size());
	result.svc_state.resize(svcs.size());
	result.svc_control_residual.resize(svcs.size());
	for (std::size_t i = 0; i < svcs.size(); ++i) {
		result.svc_q_mvar[i] = svcs[i].q_pu * data.base_mva;
		result.svc_state[i] = svcs[i].limit_state;
		result.svc_control_residual[i] = svcs[i].control_residual;
	}
	return result;
}

PowerFlowResult solve_power_flow_fd_with_lcc(CaseData& data,
											 double tolerance,
											 int max_iterations,
											 std::ostream* live_trace_output = nullptr) {
	PowerFlowResult result = solve_power_flow_fd_once(data, tolerance, max_iterations, live_trace_output);
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
		const PowerFlowResult next_result = solve_power_flow_fd_once(data, tolerance, max_iterations, nullptr);
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

PowerFlowResult solve_power_flow_fd_with_outer_controls_impl(CaseData& data,
														double tolerance,
														int max_iterations,
														std::ostream* live_trace_output = nullptr) {
	PowerFlowResult result = solve_power_flow_fd_with_lcc(data, tolerance, max_iterations, live_trace_output);
	if (!result.converged) {
		return result;
	}

	constexpr int max_control_passes = 4;
	for (int pass = 0; pass < max_control_passes; ++pass) {
		const bool shunts_changed = adjust_switched_bus_shunts(data, result);
		const bool taps_changed = adjust_ltc_taps(data, result);
		if (!shunts_changed && !taps_changed) {
			break;
		}
		seed_next_solve_from_result(data, result);
		write_trace_restart(live_trace_output,
			"outer control pass " + std::to_string(pass + 1) + " changed shunts/taps; re-solving AC equations");
		const PowerFlowResult next_result = solve_power_flow_fd_with_lcc(data, tolerance, max_iterations, nullptr);
		if (!next_result.converged) {
			break;
		}
		append_power_flow_result(result, next_result, live_trace_output);
	}
	return result;
}

std::set<int> parse_int_set(const std::string& text, const std::string& option_name) {
	std::set<int> values;
	std::stringstream stream(text);
	std::string item;
	while (std::getline(stream, item, ',')) {
		if (!item.empty()) {
			values.insert(std::stoi(item));
		}
	}
	if (values.empty()) {
		throw std::runtime_error(option_name + " requires at least one integer value");
	}
	return values;
}

std::set<std::string> parse_string_set(const std::string& text, const std::string& option_name) {
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

std::string reduction_method_label(EquivalentReductionMethod method) {
	if (method == EquivalentReductionMethod::Ward) {
		return "Ward extended";
	}
	if (method == EquivalentReductionMethod::ConstantPowerInjection) {
		return "constant-power injection";
	}
	return "none";
}

void write_reduction_summary(const EquivalentReductionOptions& options, const EquivalentReductionSummary& summary) {
	if (options.method == EquivalentReductionMethod::None) {
		return;
	}
	std::cout << "Network equivalent reduction:\n";
	if (summary.applied) {
		std::cout << "    - " << reduction_method_label(options.method) << " applied\n"
				  << "    - Retained buses: " << summary.retained_buses << "\n"
				  << "    - External buses eliminated: " << summary.external_buses << "\n"
				  << "    - Boundary buses: " << summary.boundary_buses << "\n"
				  << "    - Removed branches: " << summary.removed_branches << "\n"
				  << "    - Added branches: " << summary.added_branches << "\n"
				  << "    - Added shunts: " << summary.added_shunts << "\n";
	} else {
		std::cout << "    - " << reduction_method_label(options.method) << " requested\n"
				  << "    - No explicit external/retained selection was provided, so only the default zero-impedance reduction was applied\n";
	}
}

} // namespace

PowerFlowResult solve_power_flow_fd_with_outer_controls(CaseData& data,
																double tolerance,
																int max_iterations,
																std::ostream* live_trace_output) {
	return solve_power_flow_fd_with_outer_controls_impl(data, tolerance, max_iterations, live_trace_output);
}

#ifndef POWER_SIMULATOR_FAST_DECOUPLED_LIBRARY
int main(int argc, char** argv) {
	std::string case_path = "data/d_9nodes.dat";
	double tolerance = DEFAULT_POWER_FLOW_TOLERANCE;
	int max_iterations = 50;
	bool save_results = false;
	bool export_excel = false;
	std::string save_path;
	std::string excel_path;
	EquivalentReductionOptions reduction_options;
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
		const EquivalentReductionSummary reduction_summary = apply_equivalent_network_reduction(data, reduction_options);
		const bool use_coupled_newton = !data.lccs.empty();
		if (use_coupled_newton) {
			write_case_header(std::cout, case_path, data, "Newton-Raphson power flow");
			write_reduction_summary(reduction_options, reduction_summary);
			std::cout << "Estimated dense matrix memory: " << std::fixed << std::setprecision(2)
					  << estimate_dense_memory_gb(data) << " GB\n";
			std::cout << "Solver mode: coupled AC/DC Newton-Raphson for LCC-HVDC case via fast-decoupled entry point\n";
			std::cout << "AC convergence criteria: |dP| <= " << std::scientific << std::setprecision(4)
					  << active_power_tolerance_pu(data) << " pu (TEPA), |dQ| <= "
					  << reactive_power_tolerance_pu(data) << " pu (TEPR), controls <= "
					  << data.vlim_control_tolerance << " pu (TLVC)\n";
			std::cout << "AC divergence voltage window: [" << data.voltage_divergence_min_pu
					  << ", " << data.voltage_divergence_max_pu << "] pu (VDVN/VDVM)\n";
			std::cout << "Near-zero guard tolerance: " << std::scientific << std::setprecision(4) << TOLERANCE << "\n";
			write_convergence_trace_header(std::cout, "full Newton-Raphson");
			std::cout.flush();

			const PowerFlowResult result = solve_power_flow_newton_with_outer_controls(data, tolerance, max_iterations, &std::cout);
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
		}

		write_case_header(std::cout, case_path, data, "Fast-decoupled power flow");
		write_reduction_summary(reduction_options, reduction_summary);
		std::cout << "Estimated dense matrix memory: " << std::fixed << std::setprecision(2)
				  << estimate_dense_memory_gb(data) << " GB\n";
		std::cout << "Solver mode: sparse fast-decoupled Newton-Raphson";
		if (!data.svcs.empty() || !data.cscs.empty() || !data.ltcs.empty() || !data.psts.empty() || !data.lccs.empty()) {
			std::cout << " with Brazilian device outer controls";
		}
		std::cout << "\n";
		std::cout << "AC convergence criteria: |dP| <= " << std::scientific << std::setprecision(4)
				  << active_power_tolerance_pu(data) << " pu (TEPA), |dQ| <= "
				  << reactive_power_tolerance_pu(data) << " pu (TEPR), controls <= "
				  << data.vlim_control_tolerance << " pu (TLVC)\n";
		std::cout << "AC divergence voltage window: [" << data.voltage_divergence_min_pu
				  << ", " << data.voltage_divergence_max_pu << "] pu (VDVN/VDVM)\n";
		std::cout << "Near-zero guard tolerance: " << std::scientific << std::setprecision(4) << TOLERANCE << "\n";
		write_convergence_trace_header(std::cout, "fast-decoupled Newton-Raphson");
		std::cout.flush();

		const PowerFlowResult result = solve_power_flow_fd_with_outer_controls(data, tolerance, max_iterations, &std::cout);
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
			const std::string output_path = resolve_excel_results_path(case_path, excel_path, "fd");
			export_results_to_excel(case_path, data, result, branch_flows, excel_path, "fd");
			std::cout << "\nExported Excel results to: " << output_path << "\n";
		}

		return result.converged ? 0 : 2;
	} catch (const std::exception& ex) {
		std::cerr << "error: " << ex.what() << "\n";
		return 1;
	}
}
#endif
