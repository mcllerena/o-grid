#pragma once

#include <map>

#include "../case_data.h"
#include "../utils/power_flow_types.h"

struct BusShuntBankAggregate {
	double initial_mvar = 0.0;
	double min_mvar = 0.0;
	double max_mvar = 0.0;
};

void apply_parsed_shunts_to_buses(CaseData& data, const std::map<int, BusShuntBankAggregate>& bus_shunt_bank_totals);

bool adjust_switched_bus_shunts(CaseData& data, const PowerFlowResult& result);
