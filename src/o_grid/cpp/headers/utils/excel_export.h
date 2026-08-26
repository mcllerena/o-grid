#pragma once

#include <string>
#include <vector>

#include "../case_data.h"
#include "power_flow_types.h"

std::string default_excel_results_path(const std::string& case_path, const std::string& algorithm_suffix);

std::string resolve_excel_results_path(const std::string& case_path, const std::string& destination, const std::string& algorithm_suffix);

void export_results_to_excel(const std::string& case_path,
                             const CaseData& data,
                             const PowerFlowResult& result,
                             const std::vector<BranchFlow>& branch_flows,
                             const std::string& destination,
                             const std::string& algorithm_suffix);
