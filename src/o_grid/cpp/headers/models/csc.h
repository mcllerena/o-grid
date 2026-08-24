#pragma once

#include <complex>
#include <vector>

#include "../case_data.h"
#include "../utils/power_flow_types.h"

struct CscState {
    int device_index = 0;
    int branch_index = -1;
    int from_index = 0;
    int to_index = 0;
    double x_pu = 0.0;
    double xmin_pu = 0.0;
    double xmax_pu = 0.0;
    bool active = false;
};

struct CscFlow {
    int device_index = 0;
    int branch_index = -1;
    double p_from_mw = 0.0;
    double q_from_mvar = 0.0;
    double p_to_mw = 0.0;
    double q_to_mvar = 0.0;
    double p_loss_mw = 0.0;
    double q_loss_mvar = 0.0;
};

std::vector<CscState> build_csc_states(const CaseData& data);
bool csc_replaces_branch(const std::vector<CscState>& states, int branch_index);
void add_csc_to_ybus(std::vector<std::vector<std::complex<double>>>& ybus,
                     const std::vector<CscState>& states);
std::vector<CscFlow> calculate_csc_flows(const CaseData& data,
                                         const std::vector<double>& vm,
                                         const std::vector<double>& va);