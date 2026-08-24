#pragma once

#include "../case_data.h"
#include "../utils/power_flow_types.h"

struct LccInterfaceDeviation {
	double max_active_mw = 0.0;
	double max_reactive_mvar = 0.0;
	double max_tap_equivalent_mvar = 0.0;
};

LccInterfaceDeviation update_lcc_from_dc_solution(CaseData& data, const PowerFlowResult& result, double damping);
