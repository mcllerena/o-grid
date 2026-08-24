#include "../headers/models/csc.h"

#include <cmath>
#include <complex>
#include <map>
#include <stdexcept>

namespace {

std::map<int, int> make_bus_index(const CaseData& data) {
	std::map<int, int> bus_index;
	for (std::size_t i = 0; i < data.buses.size(); ++i) {
		bus_index[data.buses[i].id] = static_cast<int>(i);
	}
	return bus_index;
}

bool same_branch(const Branch& branch, const Csc& csc) {
	return branch.from == csc.from && branch.to == csc.to && branch.circuit == csc.circuit;
}

bool is_active_csc(const Csc& csc) {
	return csc.operation != "E" && csc.state != "D" && csc.bypass != "L" && std::abs(csc.x_pu) > TOLERANCE;
}

CscFlow calculate_flow(const CaseData& data,
					   const CscState& state,
					   const std::vector<double>& vm,
					   const std::vector<double>& va) {
	const double vm_from = vm[state.from_index];
	const double vm_to = vm[state.to_index];
	const double delta = va[state.from_index] - va[state.to_index];
	const double cross_sin = vm_from * vm_to * std::sin(delta);
	const double cross_cos = vm_from * vm_to * std::cos(delta);

	CscFlow flow;
	flow.device_index = state.device_index;
	flow.branch_index = state.branch_index;
	flow.p_from_mw = clean_output_zero(cross_sin / state.x_pu * data.base_mva);
	flow.q_from_mvar = clean_output_zero((vm_from * vm_from - cross_cos) / state.x_pu * data.base_mva);
	flow.p_to_mw = clean_output_zero(-cross_sin / state.x_pu * data.base_mva);
	flow.q_to_mvar = clean_output_zero((vm_to * vm_to - cross_cos) / state.x_pu * data.base_mva);
	flow.p_loss_mw = clean_output_zero(flow.p_from_mw + flow.p_to_mw);
	flow.q_loss_mvar = clean_output_zero(flow.q_from_mvar + flow.q_to_mvar);
	return flow;
}

} // namespace

std::vector<CscState> build_csc_states(const CaseData& data) {
	const std::map<int, int> bus_index = make_bus_index(data);
	std::vector<CscState> states;
	states.reserve(data.cscs.size());

	for (std::size_t device_index = 0; device_index < data.cscs.size(); ++device_index) {
		const Csc& csc = data.cscs[device_index];
		if (!is_active_csc(csc)) {
			continue;
		}

		const auto from_it = bus_index.find(csc.from);
		const auto to_it = bus_index.find(csc.to);
		if (from_it == bus_index.end() || to_it == bus_index.end()) {
			throw std::runtime_error("DCSC references an unknown bus");
		}

		int branch_index = -1;
		for (std::size_t i = 0; i < data.branches.size(); ++i) {
			if (same_branch(data.branches[i], csc)) {
				branch_index = static_cast<int>(i);
				break;
			}
		}
		CscState state;
		state.device_index = static_cast<int>(device_index);
		state.branch_index = branch_index;
		state.from_index = from_it->second;
		state.to_index = to_it->second;
		state.x_pu = csc.x_pu;
		state.xmin_pu = csc.xmin_pu;
		state.xmax_pu = csc.xmax_pu;
		state.active = true;
		states.push_back(state);
	}

	return states;
}

bool csc_replaces_branch(const std::vector<CscState>& states, int branch_index) {
	for (const CscState& state : states) {
		if (state.active && state.branch_index == branch_index) {
			return true;
		}
	}
	return false;
}

void add_csc_to_ybus(std::vector<std::vector<std::complex<double>>>& ybus,
					 const std::vector<CscState>& states) {
	for (const CscState& state : states) {
		if (!state.active || state.branch_index >= 0) {
			continue;
		}
		const std::complex<double> y = 1.0 / std::complex<double>(0.0, state.x_pu);
		const int f = state.from_index;
		const int t = state.to_index;
		ybus[f][f] += y;
		ybus[t][t] += y;
		ybus[f][t] -= y;
		ybus[t][f] -= y;
	}
}

std::vector<CscFlow> calculate_csc_flows(const CaseData& data,
										 const std::vector<double>& vm,
										 const std::vector<double>& va) {
	const std::vector<CscState> states = build_csc_states(data);
	std::vector<CscFlow> flows;
	flows.reserve(states.size());
	for (const CscState& state : states) {
		flows.push_back(calculate_flow(data, state, vm, va));
	}
	return flows;
}
