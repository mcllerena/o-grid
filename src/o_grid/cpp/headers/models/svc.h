#pragma once

#include <string>
#include <vector>

#include "../case_data.h"

struct SvcState {
    int device_index = 0;
    int bus_index = 0;
    int control_bus_index = 0;
    bool active = false;
    int mode = 0;
    double slope = 0.0;
    double q_pu = 0.0;
    double q_initial_pu = 0.0;
    double q_min_pu = 0.0;
    double q_max_pu = 0.0;
    double v_ref = 1.0;
    int limit_state = 0;
    double control_residual = 0.0;
};

std::vector<SvcState> build_svc_states(const CaseData& data, const std::vector<double>& vm);
void update_svc_limits(std::vector<SvcState>& svcs, const std::vector<double>& vm);
double svc_control_residual(const SvcState& svc, const std::vector<double>& vm);
double svc_control_derivative_voltage(const SvcState& svc, int bus_index, const std::vector<double>& vm);
double svc_control_derivative_q(const SvcState& svc, const std::vector<double>& vm);
std::vector<double> svc_q_injection_by_bus(const std::vector<SvcState>& svcs, std::size_t bus_count);
std::string svc_limit_label(int limit_state);
