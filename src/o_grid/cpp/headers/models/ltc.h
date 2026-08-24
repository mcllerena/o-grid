#pragma once

#include "../case_data.h"
#include "../utils/power_flow_types.h"

void apply_ltc_to_branches(CaseData& data);

bool adjust_ltc_taps(CaseData& data, const PowerFlowResult& result);
