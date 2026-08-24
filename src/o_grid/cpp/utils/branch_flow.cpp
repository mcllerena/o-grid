#include "../headers/utils/branch_flow.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <map>

#include "../headers/models/csc.h"

namespace {

std::complex<double> polar_voltage(double magnitude, double angle_rad) {
    return std::polar(magnitude, angle_rad);
}

} // namespace

std::vector<BranchFlow> calculate_branch_flows(const CaseData& data,
                                               const std::vector<double>& vm,
                                               const std::vector<double>& va) {
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
    }

    std::vector<BranchFlow> flows;
    flows.reserve(data.branches.size());

    std::map<int, CscFlow> csc_flow_by_branch;
    for (const CscFlow& flow : calculate_csc_flows(data, vm, va)) {
        csc_flow_by_branch[flow.branch_index] = flow;
    }

    for (std::size_t branch_index = 0; branch_index < data.branches.size(); ++branch_index) {
        const Branch& branch = data.branches[branch_index];
        const auto csc_flow_it = csc_flow_by_branch.find(static_cast<int>(branch_index));
        if (csc_flow_it != csc_flow_by_branch.end()) {
            const CscFlow& csc_flow = csc_flow_it->second;
            BranchFlow flow;
            flow.p_from_mw = csc_flow.p_from_mw;
            flow.q_from_mvar = csc_flow.q_from_mvar;
            flow.p_to_mw = csc_flow.p_to_mw;
            flow.q_to_mvar = csc_flow.q_to_mvar;
            flow.s_from_mva = clean_output_zero(std::hypot(flow.p_from_mw, flow.q_from_mvar));
            flow.s_to_mva = clean_output_zero(std::hypot(flow.p_to_mw, flow.q_to_mvar));
            const double max_flow_mva = std::max(flow.s_from_mva, flow.s_to_mva);
            if (branch.rate_mva > 0.0) {
                flow.loading_percent = clean_output_zero(100.0 * max_flow_mva / branch.rate_mva);
                flow.overloaded = max_flow_mva > branch.rate_mva + DISPLAY_TOLERANCE;
            }
            flow.p_loss_mw = csc_flow.p_loss_mw;
            flow.q_loss_mvar = csc_flow.q_loss_mvar;
            flows.push_back(flow);
            continue;
        }

        const std::size_t f = bus_index.at(branch.from);
        const std::size_t t = bus_index.at(branch.to);
        const std::complex<double> vf = polar_voltage(vm[f], va[f]);
        const std::complex<double> vt = polar_voltage(vm[t], va[t]);
        const std::complex<double> z(branch.r, branch.x);
        const std::complex<double> y = 1.0 / z;
        const std::complex<double> charging(0.0, branch.b / 2.0);
        const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);

        const std::complex<double> yff = (y + charging) / (tap * std::conj(tap));
        const std::complex<double> yft = -y / std::conj(tap);
        const std::complex<double> ytf = -y / tap;
        const std::complex<double> ytt = y + charging;

        const std::complex<double> ifrom = yff * vf + yft * vt;
        const std::complex<double> ito = ytf * vf + ytt * vt;
        const std::complex<double> sfrom = vf * std::conj(ifrom) * data.base_mva;
        const std::complex<double> sto = vt * std::conj(ito) * data.base_mva;

        BranchFlow flow;
        flow.p_from_mw = clean_output_zero(sfrom.real());
        flow.q_from_mvar = clean_output_zero(sfrom.imag());
        flow.p_to_mw = clean_output_zero(sto.real());
        flow.q_to_mvar = clean_output_zero(sto.imag());
        flow.s_from_mva = clean_output_zero(std::abs(sfrom));
        flow.s_to_mva = clean_output_zero(std::abs(sto));
        const double max_flow_mva = std::max(flow.s_from_mva, flow.s_to_mva);
        if (branch.rate_mva > 0.0) {
            flow.loading_percent = clean_output_zero(100.0 * max_flow_mva / branch.rate_mva);
            flow.overloaded = max_flow_mva > branch.rate_mva + DISPLAY_TOLERANCE;
        }
        flow.p_loss_mw = clean_output_zero((sfrom + sto).real());
        flow.q_loss_mvar = clean_output_zero((sfrom + sto).imag());
        flows.push_back(flow);
    }

    return flows;
}

std::string voltage_violation_label(const Bus& bus, double vm) {
    if (vm > bus.vmax + DISPLAY_TOLERANCE) {
        return "upper";
    }
    if (vm < bus.vmin - DISPLAY_TOLERANCE) {
        return "lower";
    }
    return "";
}

ViolationSummary make_violation_summary(const CaseData& data,
                                        const PowerFlowResult& result,
                                        const std::vector<BranchFlow>& branch_flows) {
    ViolationSummary summary;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        const std::string violation = voltage_violation_label(data.buses[i], result.vm[i]);
        if (violation == "upper") {
            ++summary.voltage_upper;
        } else if (violation == "lower") {
            ++summary.voltage_lower;
        }
    }

    for (const BranchFlow& flow : branch_flows) {
        if (flow.overloaded) {
            ++summary.line_overloads;
        }
    }
    return summary;
}
