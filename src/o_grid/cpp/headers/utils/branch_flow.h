#pragma once

#include <string>
#include <vector>

#include "../case_data.h"
#include "power_flow_types.h"

std::vector<BranchFlow> calculate_branch_flows(const CaseData& data,
                                               const std::vector<double>& vm,
                                               const std::vector<double>& va);

std::string voltage_violation_label(const Bus& bus, double vm);

ViolationSummary make_violation_summary(const CaseData& data,
                                        const PowerFlowResult& result,
                                        const std::vector<BranchFlow>& branch_flows);
