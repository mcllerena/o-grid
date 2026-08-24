#pragma once

#include <complex>
#include <limits>
#include <utility>
#include <vector>

struct IterationTrace {
    int iteration = 0;
    double max_dp = 0.0;
    double max_dq = 0.0;
    double max_control_residual = 0.0;
    double max_residual = 0.0;
    double max_step = 0.0;
};

struct SparseComplexEntry {
    int col = 0;
    std::complex<double> value;
};

struct SparseYbus {
    std::vector<std::vector<SparseComplexEntry>> rows;
};

struct SparseRealMatrix {
    int size = 0;
    std::vector<std::vector<std::pair<int, double>>> rows;
};

struct PowerFlowResult {
    bool converged = false;
    bool diverged = false;
    int iterations = 0;
    double max_mismatch = std::numeric_limits<double>::infinity();
    std::vector<IterationTrace> trace;
    std::vector<double> vm;
    std::vector<double> va;
    std::vector<double> p_calc;
    std::vector<double> q_calc;
    std::vector<int> vlim_controlled;
    std::vector<double> svc_q_mvar;
    std::vector<double> svc_q_initial_mvar;
    std::vector<double> svc_v_control_pu;
    std::vector<double> svc_v_ref_pu;
    std::vector<int> svc_active;
    std::vector<int> svc_state;
    std::vector<double> svc_control_residual;
};

struct BranchFlow {
    double p_from_mw = 0.0;
    double q_from_mvar = 0.0;
    double p_to_mw = 0.0;
    double q_to_mvar = 0.0;
    double s_from_mva = 0.0;
    double s_to_mva = 0.0;
    double loading_percent = 0.0;
    double p_loss_mw = 0.0;
    double q_loss_mvar = 0.0;
    bool overloaded = false;
};

struct ViolationSummary {
    int voltage_upper = 0;
    int voltage_lower = 0;
    int line_overloads = 0;
};
