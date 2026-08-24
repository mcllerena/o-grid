#pragma once

#include <set>
#include <string>

#include "../case_data.h"

enum class EquivalentReductionMethod {
	None,
	Ward,
	ConstantPowerInjection,
};

struct EquivalentReductionOptions {
	EquivalentReductionMethod method = EquivalentReductionMethod::None;
	std::set<int> retained_buses;
	std::set<int> external_buses;
	std::set<int> retained_areas;
	std::set<int> external_areas;
	std::set<std::string> retained_voltage_groups;
	std::set<std::string> external_voltage_groups;
	double zmax = 0.0;
};

struct EquivalentReductionSummary {
	EquivalentReductionMethod method = EquivalentReductionMethod::None;
	int retained_buses = 0;
	int external_buses = 0;
	int boundary_buses = 0;
	int removed_branches = 0;
	int added_branches = 0;
	int added_shunts = 0;
	bool applied = false;
};

void reduce_low_impedance_network(CaseData& data);

EquivalentReductionSummary apply_equivalent_network_reduction(CaseData& data, const EquivalentReductionOptions& options);
