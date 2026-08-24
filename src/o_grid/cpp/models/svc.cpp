#include "../headers/models/svc.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <stdexcept>

std::vector<SvcState> build_svc_states(const CaseData& data, const std::vector<double>& vm) {
	std::map<int, int> bus_index;
	for (std::size_t i = 0; i < data.buses.size(); ++i) {
		bus_index[data.buses[i].id] = static_cast<int>(i);
	}

	std::vector<SvcState> states;
	states.reserve(data.svcs.size());
	for (std::size_t i = 0; i < data.svcs.size(); ++i) {
		const Svc& device = data.svcs[i];
		const auto bus_it = bus_index.find(device.bus);
		const auto control_it = bus_index.find(device.control_bus);
		if (bus_it == bus_index.end() || control_it == bus_index.end()) {
			throw std::runtime_error("DCER references an unknown bus");
		}

		SvcState state;
		state.device_index = static_cast<int>(i);
		state.bus_index = bus_it->second;
		state.control_bus_index = control_it->second;
		state.active = data.buses[state.bus_index].type == BusType::PQ;
		state.mode = device.mode;
		state.slope = device.slope;
		state.q_initial_pu = device.q_mvar / data.base_mva;
		state.q_pu = state.active ? device.q_mvar / data.base_mva : 0.0;
		state.q_min_pu = device.qmin_mvar / data.base_mva;
		state.q_max_pu = device.qmax_mvar / data.base_mva;
		state.v_ref = vm[state.control_bus_index];
		states.push_back(state);
	}

	update_svc_limits(states, vm);
	return states;
}

void update_svc_limits(std::vector<SvcState>& svcs, const std::vector<double>& vm) {
	for (SvcState& svc : svcs) {
		svc.limit_state = 0;
		if (!svc.active) {
			svc.q_pu = 0.0;
			svc.control_residual = 0.0;
			continue;
		}

		const double limit_vm = vm[svc.control_bus_index];
		const double vm2 = limit_vm * limit_vm;
		const double lower = svc.q_min_pu * vm2;
		const double upper = svc.q_max_pu * vm2;
		double control_q = svc.q_pu;
		if (std::abs(svc.slope) > TOLERANCE) {
			if (svc.mode == 1) {
				control_q = (svc.v_ref - vm[svc.control_bus_index]) * vm[svc.bus_index] / svc.slope;
			} else {
				control_q = (svc.v_ref - vm[svc.control_bus_index]) / svc.slope;
			}
		}
		if (control_q < lower) {
			svc.q_pu = lower;
			svc.limit_state = -1;
		} else if (control_q > upper) {
			svc.q_pu = upper;
			svc.limit_state = 1;
		}
		svc.control_residual = svc_control_residual(svc, vm);
	}
}

double svc_control_residual(const SvcState& svc, const std::vector<double>& vm) {
	if (!svc.active) {
		return 0.0;
	}

	const double comp_vm = vm[svc.control_bus_index];
	if (svc.limit_state == -1) {
		return svc.q_min_pu * comp_vm * comp_vm - svc.q_pu;
	}
	if (svc.limit_state == 1) {
		return svc.q_max_pu * comp_vm * comp_vm - svc.q_pu;
	}
	if (svc.mode == 1) {
		return vm[svc.control_bus_index] - svc.v_ref + svc.q_pu * svc.slope / comp_vm;
	}
	return vm[svc.control_bus_index] - svc.v_ref + svc.q_pu * svc.slope;
}

double svc_control_derivative_voltage(const SvcState& svc, int bus_index, const std::vector<double>& vm) {
	if (!svc.active) {
		return 0.0;
	}

	double derivative = 0.0;
	if (svc.limit_state == -1) {
		if (bus_index == svc.control_bus_index) {
			derivative += 2.0 * svc.q_min_pu * vm[svc.control_bus_index];
		}
	} else if (svc.limit_state == 1) {
		if (bus_index == svc.control_bus_index) {
			derivative += 2.0 * svc.q_max_pu * vm[svc.control_bus_index];
		}
	} else {
		if (bus_index == svc.control_bus_index) {
			derivative += 1.0;
		}
		if (svc.mode == 1 && bus_index == svc.bus_index) {
			const double comp_vm = std::max(vm[svc.bus_index], DISPLAY_TOLERANCE);
			derivative -= svc.q_pu * svc.slope / (comp_vm * comp_vm);
		}
	}
	return derivative;
}

double svc_control_derivative_q(const SvcState& svc, const std::vector<double>& vm) {
	if (!svc.active) {
		return 0.0;
	}
	if (svc.limit_state != 0) {
		return -1.0;
	}
	if (svc.mode == 1) {
		return svc.slope / std::max(vm[svc.bus_index], DISPLAY_TOLERANCE);
	}
	return svc.slope;
}

std::vector<double> svc_q_injection_by_bus(const std::vector<SvcState>& svcs, std::size_t bus_count) {
	std::vector<double> q_by_bus(bus_count, 0.0);
	for (const SvcState& svc : svcs) {
		if (svc.active) {
			q_by_bus[svc.bus_index] += svc.q_pu;
		}
	}
	return q_by_bus;
}

std::string svc_limit_label(int limit_state) {
	if (limit_state < 0) {
		return "lower";
	}
	if (limit_state > 0) {
		return "upper";
	}
	return "control";
}
