#pragma once

#include <iosfwd>
#include <string>
#include <vector>

#include "../case_data.h"
#include "power_flow_types.h"

std::string default_results_path(const std::string& case_path);

int count_generator_buses(const CaseData& data);
int count_load_buses(const CaseData& data);
int count_slack_buses(const CaseData& data);
int count_pq_buses(const CaseData& data);

double estimate_dense_memory_gb(const CaseData& data);

void write_convergence_trace_header(std::ostream& output);
void write_convergence_trace_header(std::ostream& output, const std::string& solver_name);
void write_convergence_trace_row(std::ostream& output, const IterationTrace& item);
void write_convergence_trace(std::ostream& output, const PowerFlowResult& result);
void write_convergence_trace(std::ostream& output, const PowerFlowResult& result, const std::string& solver_name);

void write_violation_summary(std::ostream& output, const ViolationSummary& summary);
void write_power_balance_summary(std::ostream& output,
                                 const CaseData& data,
                                 const PowerFlowResult& result,
                                 const std::vector<BranchFlow>& branch_flows);
double lcc_dc_loss_mw(const Lcc& lcc);
double lcc_idc_pu(const Lcc& lcc);
double lcc_report_tap_rectifier(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result);
double lcc_report_tap_inverter(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result);
void write_csc_results(std::ostream& output, const CaseData& data, const PowerFlowResult& result);
void write_case_header(std::ostream& output, const std::string& case_path, const CaseData& data);
void write_case_header(std::ostream& output, const std::string& case_path, const CaseData& data, const std::string& solver_name);
void write_summary(std::ostream& output,
                   const std::string& case_path,
                   const CaseData& data,
                   const PowerFlowResult& result);
void write_full_report(std::ostream& output,
                       const std::string& case_path,
                       const CaseData& data,
                       const PowerFlowResult& result,
                       const std::vector<BranchFlow>& branch_flows);
