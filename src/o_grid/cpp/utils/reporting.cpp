#include "../headers/utils/reporting.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <complex>
#include <iomanip>
#include <iostream>
#include <map>

#include "../headers/models/csc.h"
#include "../headers/models/svc.h"
#include "../headers/utils/branch_flow.h"

std::string default_results_path(const std::string& case_path) {
    const std::size_t slash = case_path.find_last_of("\\/");
    const std::size_t start = slash == std::string::npos ? 0 : slash + 1;
    const std::size_t dot = case_path.find_last_of('.');
    const std::size_t end = dot == std::string::npos || dot < start ? case_path.size() : dot;
    return case_path.substr(start, end - start) + "_results.txt";
}

int count_generator_buses(const CaseData& data) {
    int count = 0;
    for (const Bus& bus : data.buses) {
        if (std::abs(bus.pg_mw) > DISPLAY_TOLERANCE || std::abs(bus.qg_mvar) > DISPLAY_TOLERANCE ||
            (bus.type == BusType::PV && !bus.zero_generation_voltage_control) || bus.type == BusType::Slack) {
            ++count;
        }
    }
    return count;
}

int count_load_buses(const CaseData& data) {
    int count = 0;
    for (const Bus& bus : data.buses) {
        if (std::abs(bus.pl_mw) > DISPLAY_TOLERANCE || std::abs(bus.ql_mvar) > DISPLAY_TOLERANCE) {
            ++count;
        }
    }
    return count;
}

double total_scheduled_generation_mw(const CaseData& data) {
    double total = 0.0;
    for (const Bus& bus : data.buses) {
        total += bus.pg_mw;
    }
    return total;
}

double total_load_mw(const CaseData& data) {
    double total = 0.0;
    for (const Bus& bus : data.buses) {
        total += bus.pl_mw;
    }
    return total;
}

double total_solved_generation_mw(const CaseData& data, const PowerFlowResult& result) {
    if (result.p_calc.size() < data.buses.size()) {
        return total_scheduled_generation_mw(data);
    }

    double total = 0.0;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        total += result.p_calc[i] * data.base_mva + data.buses[i].pl_mw;
    }
    return total;
}

double total_branch_loss_mw(const std::vector<BranchFlow>& branch_flows) {
    double total = 0.0;
    for (const BranchFlow& flow : branch_flows) {
        total += flow.p_loss_mw;
    }
    return total;
}

int count_slack_buses(const CaseData& data) {
    int count = 0;
    for (const Bus& bus : data.buses) {
        if (bus.type == BusType::Slack) {
            ++count;
        }
    }
    return count;
}

int count_pq_buses(const CaseData& data) {
    int count = 0;
    for (const Bus& bus : data.buses) {
        if (bus.type == BusType::PQ) {
            ++count;
        }
    }
    return count;
}

std::string bus_type_name(const Bus& bus) {
    if (bus.type == BusType::Slack) {
        return "Slack";
    }
    if (bus.type == BusType::PV) {
        return "PV";
    }
    return "PQ";
}

double estimate_dense_memory_gb(const CaseData& data) {
    const double nbus = static_cast<double>(data.buses.size());
    const double nstate = static_cast<double>(data.buses.size() - count_slack_buses(data) + count_pq_buses(data));
    const double ybus_bytes = nbus * nbus * sizeof(std::complex<double>);
    const double jacobian_bytes = nstate * nstate * sizeof(double);
    return (ybus_bytes + jacobian_bytes) / (1024.0 * 1024.0 * 1024.0);
}

void write_convergence_trace_header(std::ostream& output) {
    write_convergence_trace_header(output, "full Newton-Raphson");
}

void write_convergence_trace_header(std::ostream& output, const std::string& solver_name) {
    output << "\nIteration-by-iteration convergence trace (" << solver_name << ")\n";
    output << std::string(62, '-') << "\n";
    output << std::right
           << std::setw(4) << "it" << "  "
           << std::setw(12) << "max|dP|" << "  "
           << std::setw(12) << "max|dQ|" << "  "
           << std::setw(12) << "max|R|" << "  "
           << std::setw(12) << "max|dx|" << "\n";
    output << std::setw(4) << "----" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "\n";
}

void write_convergence_trace_row(std::ostream& output, const IterationTrace& item) {
    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::scientific << std::setprecision(4)
           << std::setw(4) << item.iteration << "  "
           << std::setw(12) << item.max_dp << "  "
           << std::setw(12) << item.max_dq << "  "
           << std::setw(12) << item.max_residual << "  "
           << std::setw(12) << item.max_step << "\n";
    output.flags(flags);
    output.precision(precision);
}

void write_convergence_trace(std::ostream& output, const PowerFlowResult& result) {
    write_convergence_trace(output, result, "full Newton-Raphson");
}

void write_convergence_trace(std::ostream& output, const PowerFlowResult& result, const std::string& solver_name) {
    output << "\nIteration-by-iteration convergence trace (" << solver_name << ")\n";
    output << std::string(62, '-') << "\n";
    output << std::right
           << std::setw(4) << "it" << "  "
           << std::setw(12) << "max|dP|" << "  "
           << std::setw(12) << "max|dQ|" << "  "
           << std::setw(12) << "max|R|" << "  "
           << std::setw(12) << "max|dx|" << "\n";
    output << std::setw(4) << "----" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "  "
           << std::setw(12) << "------------" << "\n";

    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::scientific << std::setprecision(4);
    for (const IterationTrace& item : result.trace) {
        output << std::setw(4) << item.iteration << "  "
               << std::setw(12) << item.max_dp << "  "
               << std::setw(12) << item.max_dq << "  "
               << std::setw(12) << item.max_residual << "  "
               << std::setw(12) << item.max_step << "\n";
    }
    output.flags(flags);
    output.precision(precision);
    output << std::string(62, '-') << "\n";
}

void write_violation_summary(std::ostream& output, const ViolationSummary& summary) {
    output << "Voltage upper violations: " << summary.voltage_upper << "\n";
    output << "Voltage lower violations: " << summary.voltage_lower << "\n";
    output << "Line flow overloads: " << summary.line_overloads << "\n";
}

void write_power_balance_summary(std::ostream& output,
                                 const CaseData& data,
                                 const PowerFlowResult& result,
                                 const std::vector<BranchFlow>& branch_flows) {
    const double scheduled_generation_mw = total_scheduled_generation_mw(data);
    const double solved_generation_mw = total_solved_generation_mw(data, result);
    const double load_mw = total_load_mw(data);
    const double branch_loss_mw = total_branch_loss_mw(branch_flows);
    const double balance_mw = solved_generation_mw - load_mw - branch_loss_mw;

    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(3);
    output << "Scheduled generation: " << scheduled_generation_mw << " MW\n";
    output << "Solved generation: " << solved_generation_mw << " MW\n";
    output << "Total load: " << load_mw << " MW\n";
    output << "Branch active losses: " << branch_loss_mw << " MW\n";
    output << "Generation - load - branch losses: " << balance_mw << " MW\n";
    output.flags(flags);
    output.precision(precision);
}

void write_case_header(std::ostream& output, const std::string& case_path, const CaseData& data) {
    write_case_header(output, case_path, data, "Newton-Raphson power flow");
}

void write_case_header(std::ostream& output, const std::string& case_path, const CaseData& data, const std::string& solver_name) {
    output << solver_name << "\n";
    output << "Case: " << case_path << "\n";
    output << "Base MVA: " << data.base_mva << "\n";
    const std::size_t original_bus_count = data.original_buses.empty() ? data.buses.size() : data.original_buses.size();
    output << "Buses: " << original_bus_count << "\n";
    output << "Buses after reduction: " << data.buses.size() << "\n";
    output << "Branches: " << data.branches.size() << "\n";
    output << "Generator buses: " << count_generator_buses(data) << "\n";
    output << "Load buses: " << count_load_buses(data) << "\n";
    output << "Bus shunts: " << data.bus_shunts.size() << "\n";
    output << "Line shunts: " << data.line_shunts.size() << "\n";
    output << "Individual loads: " << data.individual_loads.size() << "\n";
    output << "SVC devices: " << data.svcs.size() << "\n";
    output << "DCSC/TCSC devices: " << data.cscs.size() << "\n";
    output << "LTC transformers: " << data.ltcs.size() << "\n";
    output << "PST transformers: " << data.psts.size() << "\n";
    output << "LCC-HVDC links: " << data.lccs.size() << "\n";
}

void write_summary(std::ostream& output,
                   const std::string& case_path,
                   const CaseData& data,
                   const PowerFlowResult& result) {
    write_case_header(output, case_path, data);
    output << "Converged: " << (result.converged ? "yes" : "no") << "\n";
    output << "Iterations: " << result.iterations << "\n";
    output << "Max mismatch: " << std::scientific << result.max_mismatch << " pu\n";
    const std::vector<BranchFlow> branch_flows = calculate_branch_flows(data, result.vm, result.va);
    write_power_balance_summary(output, data, result, branch_flows);
    write_convergence_trace(output, result);
}

void write_csc_results(std::ostream& output, const CaseData& data, const PowerFlowResult& result) {
    if (data.cscs.empty()) {
        return;
    }

    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(6);

    const std::vector<CscFlow> csc_flows = calculate_csc_flows(data, result.vm, result.va);
    std::map<int, CscFlow> flow_by_device;
    for (const CscFlow& flow : csc_flows) {
        flow_by_device[flow.device_index] = flow;
    }

    output << "\nDCSC/TCSC results\n";
    output << std::right
           << std::setw(6) << "Device" << "  "
           << std::setw(6) << "From" << "  "
           << std::setw(6) << "To" << "  "
           << std::setw(7) << "Circuit" << "  "
           << std::setw(5) << "Mode" << "  "
           << std::setw(10) << "X(pu)" << "  "
           << std::setw(10) << "Xmin(pu)" << "  "
           << std::setw(10) << "Xmax(pu)" << "  "
           << std::setw(12) << "Pfrom(MW)" << "  "
           << std::setw(13) << "Qfrom(MVAr)" << "  "
           << std::setw(10) << "Pto(MW)" << "  "
           << std::setw(11) << "Qto(MVAr)" << "  "
           << std::setw(8) << "Status" << "\n";
    output << std::string(135, '-') << "\n";
    for (std::size_t i = 0; i < data.cscs.size(); ++i) {
        const Csc& csc = data.cscs[i];
        const auto flow_it = flow_by_device.find(static_cast<int>(i));
        const bool in_service = flow_it != flow_by_device.end();
        const CscFlow flow = in_service ? flow_it->second : CscFlow{};
        output << std::setw(6) << i + 1 << "  "
               << std::setw(6) << csc.from << "  "
               << std::setw(6) << csc.to << "  "
               << std::setw(7) << csc.circuit << "  "
               << std::setw(5) << csc.mode << "  "
               << std::setw(10) << csc.x_pu << "  "
               << std::setw(10) << csc.xmin_pu << "  "
               << std::setw(10) << csc.xmax_pu << "  "
               << std::setw(12) << flow.p_from_mw << "  "
               << std::setw(13) << flow.q_from_mvar << "  "
               << std::setw(10) << flow.p_to_mw << "  "
               << std::setw(11) << flow.q_to_mvar << "  "
               << std::setw(8) << (in_service ? "InSvc" : "Bypass") << "\n";
    }

    output.flags(flags);
    output.precision(precision);
}

void write_ltc_results(std::ostream& output, const CaseData& data, const PowerFlowResult& result) {
    if (data.ltcs.empty()) {
        return;
    }

    const std::vector<BranchFlow> branch_flows = calculate_branch_flows(data, result.vm, result.va);
    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(6);

    output << "\nLTC transformer results\n";
    output << std::right
           << std::setw(6) << "Device" << "  "
           << std::setw(6) << "From" << "  "
           << std::setw(6) << "To" << "  "
           << std::setw(8) << "CtrlBus" << "  "
           << std::setw(10) << "Tap" << "  "
           << std::setw(10) << "TapMin" << "  "
           << std::setw(10) << "TapMax" << "  "
           << std::setw(10) << "Vtarget" << "  "
           << std::setw(12) << "Pfrom(MW)" << "  "
           << std::setw(13) << "Qfrom(MVAr)" << "  "
           << std::setw(10) << "Pto(MW)" << "  "
           << std::setw(11) << "Qto(MVAr)" << "\n";
    output << std::string(126, '-') << "\n";
    for (std::size_t i = 0; i < data.ltcs.size(); ++i) {
        const Ltc& ltc = data.ltcs[i];
        BranchFlow flow;
        if (ltc.branch_index >= 0 && static_cast<std::size_t>(ltc.branch_index) < branch_flows.size()) {
            flow = branch_flows[static_cast<std::size_t>(ltc.branch_index)];
        }
        output << std::setw(6) << i + 1 << "  "
               << std::setw(6) << ltc.from << "  "
               << std::setw(6) << ltc.to << "  "
               << std::setw(8) << ltc.control_bus << "  "
               << std::setw(10) << ltc.tap << "  "
               << std::setw(10) << ltc.tap_min << "  "
               << std::setw(10) << ltc.tap_max << "  "
               << std::setw(10) << ltc.v_target << "  "
               << std::setw(12) << flow.p_from_mw << "  "
               << std::setw(13) << flow.q_from_mvar << "  "
               << std::setw(10) << flow.p_to_mw << "  "
               << std::setw(11) << flow.q_to_mvar << "\n";
    }

    output.flags(flags);
    output.precision(precision);
}

void write_pst_results(std::ostream& output, const CaseData& data, const PowerFlowResult& result) {
    if (data.psts.empty()) {
        return;
    }

    const std::vector<BranchFlow> branch_flows = calculate_branch_flows(data, result.vm, result.va);
    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(6);

    output << "\nPST transformer results\n";
    output << std::right
           << std::setw(6) << "Device" << "  "
           << std::setw(6) << "From" << "  "
           << std::setw(6) << "To" << "  "
           << std::setw(8) << "CtrlBus" << "  "
           << std::setw(11) << "Shift(deg)" << "  "
           << std::setw(12) << "Ptarget(MW)" << "  "
           << std::setw(12) << "Pfrom(MW)" << "  "
           << std::setw(13) << "Qfrom(MVAr)" << "  "
           << std::setw(10) << "Pto(MW)" << "  "
           << std::setw(11) << "Qto(MVAr)" << "\n";
    output << std::string(111, '-') << "\n";
    for (std::size_t i = 0; i < data.psts.size(); ++i) {
        const Pst& pst = data.psts[i];
        BranchFlow flow;
        if (pst.branch_index >= 0 && static_cast<std::size_t>(pst.branch_index) < branch_flows.size()) {
            flow = branch_flows[static_cast<std::size_t>(pst.branch_index)];
        }
        output << std::setw(6) << i + 1 << "  "
               << std::setw(6) << pst.from << "  "
               << std::setw(6) << pst.to << "  "
               << std::setw(8) << pst.control_bus << "  "
               << std::setw(11) << pst.phase_rad * 180.0 / kPi << "  "
               << std::setw(12) << pst.p_target_mw << "  "
               << std::setw(12) << flow.p_from_mw << "  "
               << std::setw(13) << flow.q_from_mvar << "  "
               << std::setw(10) << flow.p_to_mw << "  "
               << std::setw(11) << flow.q_to_mvar << "\n";
    }

    output.flags(flags);
    output.precision(precision);
}

double bus_voltage(const CaseData& data, const PowerFlowResult& result, int bus_id) {
    for (std::size_t i = 0; i < data.buses.size() && i < result.vm.size(); ++i) {
        if (data.buses[i].id == bus_id) {
            return result.vm[i];
        }
    }
    return 1.0;
}

double commutation_angle_deg(double angle_deg,
                             double pdc_mw,
                             double vdc_kv,
                             double x_comm,
                             double tap,
                             double terminal_voltage_kv) {
    if (std::abs(vdc_kv) <= TOLERANCE || x_comm <= TOLERANCE || tap <= TOLERANCE || terminal_voltage_kv <= TOLERANCE) {
        return 0.0;
    }

    const double dc_current_ka = std::abs(pdc_mw / vdc_kv);
    if (dc_current_ka <= TOLERANCE) {
        return 0.0;
    }

    const double angle_rad = angle_deg * kPi / 180.0;
    const double acos_argument = std::cos(angle_rad) - std::sqrt(2.0) * x_comm * dc_current_ka /
        (tap * terminal_voltage_kv);
    const double clamped_argument = std::max(-1.0, std::min(1.0, acos_argument));
    return (std::acos(clamped_argument) - angle_rad) * 180.0 / kPi;
}

double rectifier_commutation_angle_deg(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    if (lcc.mu_rectifier_deg > 0.0 || std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return lcc.mu_rectifier_deg;
    }
    const double vterm_kv = bus_voltage(data, result, lcc.rectifier_bus) * lcc.rectifier_bridge_voltage_kv;
    return commutation_angle_deg(lcc.alpha_deg, lcc.pdc_mw, lcc.vdc_rectifier_kv, lcc.xcr, lcc.tap_rectifier, vterm_kv);
}

double inverter_commutation_angle_deg(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    if (lcc.mu_inverter_deg > 0.0 || std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return lcc.mu_inverter_deg;
    }
    const double vterm_kv = bus_voltage(data, result, lcc.inverter_bus) * lcc.inverter_bridge_voltage_kv;
    return commutation_angle_deg(lcc.gamma_deg, lcc.pdc_mw, lcc.vdc_inverter_kv, lcc.xci, lcc.tap_inverter, vterm_kv);
}

std::string bus_name(const CaseData& data, int bus_id) {
    for (const Bus& bus : data.buses) {
        if (bus.id == bus_id) {
            return bus.name;
        }
    }
    return "";
}

int lcc_pole_number(const Lcc& lcc, std::size_t link_index) {
    int value = 0;
    int multiplier = 1;
    bool found_digit = false;
    for (auto it = lcc.name.rbegin(); it != lcc.name.rend(); ++it) {
        const unsigned char character = static_cast<unsigned char>(*it);
        if (std::isdigit(character)) {
            value += (*it - '0') * multiplier;
            multiplier *= 10;
            found_digit = true;
        } else if (found_digit) {
            break;
        }
    }
    return found_digit ? value : static_cast<int>(link_index + 1);
}

std::vector<std::size_t> lcc_output_order(const CaseData& data) {
    std::vector<std::size_t> order(data.lccs.size());
    for (std::size_t i = 0; i < order.size(); ++i) {
        order[i] = i;
    }
    std::sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right) {
        const int left_key = data.lccs[left].link_id > 0 ? data.lccs[left].link_id : static_cast<int>(left + 1);
        const int right_key = data.lccs[right].link_id > 0 ? data.lccs[right].link_id : static_cast<int>(right + 1);
        return left_key < right_key;
    });
    return order;
}

double lcc_dc_loss_mw(const Lcc& lcc) {
    if (std::abs(lcc.pdc_mw) <= TOLERANCE || std::abs(lcc.vdc_rectifier_kv) <= TOLERANCE) {
        return 0.0;
    }
    const double dc_current_ka = std::abs(lcc.pdc_mw / lcc.vdc_rectifier_kv);
    return dc_current_ka * dc_current_ka * std::max(0.0, lcc.rdc);
}

double lcc_idc_pu(const Lcc& lcc) {
    if (std::abs(lcc.idc_a) <= TOLERANCE || lcc.power_base_mw <= TOLERANCE || lcc.vbase_kv <= TOLERANCE) {
        return 0.0;
    }
    const double base_current_ka = lcc.power_base_mw / lcc.vbase_kv;
    return base_current_ka > TOLERANCE ? std::abs(lcc.idc_a) / 1000.0 / base_current_ka : 0.0;
}

double lcc_rectifier_dc_voltage_pu(const Lcc& lcc) {
    if (std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return 1.0;
    }
    return lcc.vbase_kv > TOLERANCE ? std::abs(lcc.vdc_rectifier_kv) / lcc.vbase_kv : 1.0;
}

double lcc_inverter_dc_voltage_pu(const Lcc& lcc) {
    if (std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return 1.0;
    }
    return lcc.vbase_kv > TOLERANCE ? std::abs(lcc.vdc_inverter_kv) / lcc.vbase_kv : 1.0;
}

double lcc_report_tap_rectifier(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    (void)data;
    (void)result;
    if (std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return 1.0;
    }
    return lcc.tap_rectifier;
}

double lcc_report_tap_inverter(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    (void)data;
    (void)result;
    if (std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return 1.0;
    }
    return lcc.tap_inverter;
}

void write_lcc_results(std::ostream& output, const CaseData& data, const PowerFlowResult& result) {
    if (data.lccs.empty()) {
        return;
    }

    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(6);

    output << "\nLCC-HVDC results\n";
    output << "Bus#\tBusName\tVolt(pu)\tType\tPole#\tControl\tP(MW)\tQ(MVAr)\tLoss(MW)\tVdc(kV)\tIdc(pu)\tIdc(A)\tAlpha(deg)\tMu(deg)\tPhi(deg)\tTap\tStatus\n";
    const std::vector<std::size_t> order = lcc_output_order(data);
    for (std::size_t order_index = 0; order_index < order.size(); ++order_index) {
        const std::size_t i = order[order_index];
        const Lcc& lcc = data.lccs[i];
        const double mu_rectifier_deg = rectifier_commutation_angle_deg(lcc, data, result);
        const double mu_inverter_deg = inverter_commutation_angle_deg(lcc, data, result);
        const double tap_rectifier = lcc_report_tap_rectifier(lcc, data, result);
        const double tap_inverter = lcc_report_tap_inverter(lcc, data, result);
         const double loss_mw = lcc_dc_loss_mw(lcc);
         const double idc_pu = lcc_idc_pu(lcc);
         const double inverter_p_mw = -lcc.p_inverter_mw;
         const std::string status = std::abs(lcc.pdc_mw) > TOLERANCE ? "ON" : "OFF";
         const int pole = lcc_pole_number(lcc, i);
         output << lcc.rectifier_bus << '\t'
             << bus_name(data, lcc.rectifier_bus) << '\t'
             << clean_output_zero(lcc_rectifier_dc_voltage_pu(lcc)) << '\t'
             << "Rectifier" << '\t'
             << pole << '\t'
             << "Power" << '\t'
             << clean_output_zero(lcc.p_rectifier_mw) << '\t'
             << clean_output_zero(lcc.q_rectifier_mvar) << '\t'
             << clean_output_zero(loss_mw) << '\t'
             << clean_output_zero(lcc.vdc_rectifier_kv) << '\t'
             << clean_output_zero(idc_pu) << '\t'
             << clean_output_zero(lcc.idc_a) << '\t'
             << clean_output_zero(lcc.alpha_deg) << '\t'
             << clean_output_zero(mu_rectifier_deg) << '\t'
             << "-" << '\t'
             << clean_output_zero(tap_rectifier) << '\t'
             << status << "\n";
         output << lcc.inverter_bus << '\t'
             << bus_name(data, lcc.inverter_bus) << '\t'
             << clean_output_zero(lcc_inverter_dc_voltage_pu(lcc)) << '\t'
             << "Inverter" << '\t'
             << pole << '\t'
             << "-" << '\t'
             << clean_output_zero(inverter_p_mw) << '\t'
             << clean_output_zero(lcc.q_inverter_mvar) << '\t'
             << clean_output_zero(loss_mw) << '\t'
             << clean_output_zero(lcc.vdc_inverter_kv) << '\t'
             << clean_output_zero(-idc_pu) << '\t'
             << clean_output_zero(-lcc.idc_a) << '\t'
             << clean_output_zero(lcc.gamma_deg) << '\t'
             << clean_output_zero(mu_inverter_deg) << '\t'
             << "-" << '\t'
             << clean_output_zero(tap_inverter) << '\t'
             << status << "\n";
    }

    output.flags(flags);
    output.precision(precision);
}

struct BusMismatchRow {
    int bus = 0;
    double dp_mw = 0.0;
    double dq_mvar = 0.0;
    double max_abs = 0.0;
};

void write_mismatch_diagnostics(std::ostream& output, const CaseData& data, const PowerFlowResult& result) {
    if (result.p_calc.size() != data.buses.size() || result.q_calc.size() != data.buses.size()) {
        return;
    }

    std::vector<double> p_spec_mw(data.buses.size());
    std::vector<double> q_spec_mvar(data.buses.size());
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
        p_spec_mw[i] = data.buses[i].pg_mw - data.buses[i].pl_mw;
        q_spec_mvar[i] = data.buses[i].qg_mvar - data.buses[i].ql_mvar;
    }
    for (const Lcc& lcc : data.lccs) {
        const auto rectifier_it = bus_index.find(lcc.rectifier_bus);
        if (rectifier_it != bus_index.end()) {
            p_spec_mw[rectifier_it->second] -= lcc.p_rectifier_mw;
            q_spec_mvar[rectifier_it->second] -= lcc.q_rectifier_mvar;
        }
        const auto inverter_it = bus_index.find(lcc.inverter_bus);
        if (inverter_it != bus_index.end()) {
            p_spec_mw[inverter_it->second] += lcc.p_inverter_mw;
            q_spec_mvar[inverter_it->second] -= lcc.q_inverter_mvar;
        }
    }
    for (std::size_t i = 0; i < data.svcs.size() && i < result.svc_q_mvar.size(); ++i) {
        const auto it = bus_index.find(data.svcs[i].bus);
        if (it != bus_index.end()) {
            q_spec_mvar[it->second] += result.svc_q_mvar[i];
        }
    }

    std::vector<BusMismatchRow> rows;
    rows.reserve(data.buses.size());
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        BusMismatchRow row;
        row.bus = data.buses[i].id;
        row.dp_mw = p_spec_mw[i] - result.p_calc[i] * data.base_mva;
        row.dq_mvar = q_spec_mvar[i] - result.q_calc[i] * data.base_mva;
        if (data.buses[i].type == BusType::Slack) {
            row.dp_mw = 0.0;
            row.dq_mvar = 0.0;
        } else if (data.buses[i].type == BusType::PV) {
            row.dq_mvar = 0.0;
        }
        row.max_abs = std::max(std::abs(row.dp_mw), std::abs(row.dq_mvar));
        rows.push_back(row);
    }
    std::sort(rows.begin(), rows.end(), [](const BusMismatchRow& lhs, const BusMismatchRow& rhs) {
        return lhs.max_abs > rhs.max_abs;
    });

    const std::ios::fmtflags flags = output.flags();
    const std::streamsize precision = output.precision();
    output << std::fixed << std::setprecision(6);
    output << "\nLargest solved-equation mismatches\n";
    output << std::right
           << std::setw(6) << "Bus" << "  "
           << std::setw(14) << "dP(MW)" << "  "
           << std::setw(14) << "dQ(MVAr)" << "\n";
    output << std::string(40, '-') << "\n";
    const std::size_t limit = std::min<std::size_t>(10, rows.size());
    for (std::size_t i = 0; i < limit; ++i) {
        output << std::setw(6) << rows[i].bus << "  "
               << std::setw(14) << clean_output_zero(rows[i].dp_mw) << "  "
               << std::setw(14) << clean_output_zero(rows[i].dq_mvar) << "\n";
    }
    output.flags(flags);
    output.precision(precision);
}

void write_full_report(std::ostream& output,
                       const std::string& case_path,
                       const CaseData& data,
                       const PowerFlowResult& result,
                       const std::vector<BranchFlow>& branch_flows) {
    write_summary(output, case_path, data, result);
    write_violation_summary(output, make_violation_summary(data, result, branch_flows));
    output << "\nBus results\n";

    output << std::fixed << std::setprecision(6);
    output << std::right
           << std::setw(3) << "Bus" << "  "
            << std::setw(8) << "Type" << "  "
            << std::setw(5) << "Area" << "  "
            << std::setw(6) << "InServ" << "  "
           << std::setw(10) << "Vm(pu)" << "  "
            << std::setw(10) << "Vm(kV)" << "  "
           << std::setw(9) << "Va(deg)" << "  "
           << std::setw(14) << "Pg(MW)" << "  "
           << std::setw(14) << "Qg(MVAr)" << "  "
           << std::setw(12) << "Pl(MW)" << "  "
           << std::setw(13) << "Ql(MVAr)" << "  "
            << std::setw(8) << "Vmn" << "  "
            << std::setw(8) << "Vmx" << "  "
           << std::setw(10) << "Violation" << "\n";
        output << std::string(153, '-') << "\n";
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        const double pg_mw = clean_output_zero(result.p_calc[i] * data.base_mva + data.buses[i].pl_mw);
        const double qg_mvar = clean_output_zero(result.q_calc[i] * data.base_mva + data.buses[i].ql_mvar);
        const std::string voltage_violation = voltage_violation_label(data.buses[i], result.vm[i]);
        const double vm_kv = data.buses[i].base_kv > 0.0 ? result.vm[i] * data.buses[i].base_kv : 0.0;
        output << std::setw(3) << data.buses[i].id << "  "
               << std::setw(8) << bus_type_name(data.buses[i]) << "  "
               << std::setw(5) << data.buses[i].area << "  "
               << std::setw(6) << (data.buses[i].in_service ? "ON" : "OFF") << "  "
               << std::setw(10) << result.vm[i] << "  "
               << std::setw(10) << (data.buses[i].base_kv > 0.0 ? clean_output_zero(vm_kv) : 0.0) << "  "
               << std::setw(9) << result.va[i] * 180.0 / kPi << "  "
               << std::setw(14) << pg_mw << "  "
               << std::setw(14) << qg_mvar << "  "
               << std::setw(12) << data.buses[i].pl_mw << "  "
               << std::setw(13) << data.buses[i].ql_mvar << "  "
               << std::setw(8) << data.buses[i].vmin << "  "
               << std::setw(8) << data.buses[i].vmax << "  "
               << std::setw(10) << voltage_violation << "\n";
    }

    if (!data.svcs.empty()) {
        output << "\nSVC/DCER results\n";
        output << std::right
             << std::setw(6) << "SVC" << "  "
               << std::setw(6) << "Bus" << "  "
             << std::setw(14) << "Name" << "  "
             << std::setw(8) << "CtrlBus" << "  "
               << std::setw(5) << "Mode" << "  "
             << std::setw(11) << "Voltage" << "  "
             << std::setw(10) << "Vref" << "  "
             << std::setw(10) << "Slope%" << "  "
               << std::setw(13) << "Qsvc(MVAr)" << "  "
             << std::setw(13) << "Qinit(MVAr)" << "  "
             << std::setw(13) << "DeltaQ(MVAr)" << "  "
               << std::setw(12) << "Qmin(MVAr)" << "  "
               << std::setw(12) << "Qmax(MVAr)" << "  "
             << std::setw(9) << "Status" << "  "
             << std::setw(12) << "EqResidual" << "\n";
         output << std::string(169, '-') << "\n";
        for (std::size_t i = 0; i < data.svcs.size(); ++i) {
            const Svc& svc = data.svcs[i];
            const double qsvc = i < result.svc_q_mvar.size() ? clean_output_zero(result.svc_q_mvar[i]) : 0.0;
             const double qinit = i < result.svc_q_initial_mvar.size() ? clean_output_zero(result.svc_q_initial_mvar[i]) : svc.q_mvar;
             const double voltage = i < result.svc_v_control_pu.size() ? clean_output_zero(result.svc_v_control_pu[i]) : 0.0;
             const double vref = i < result.svc_v_ref_pu.size() ? clean_output_zero(result.svc_v_ref_pu[i]) : 0.0;
            const int state = i < result.svc_state.size() ? result.svc_state[i] : 0;
            const double residual = i < result.svc_control_residual.size() ? result.svc_control_residual[i] : 0.0;
            output << std::setw(6) << i + 1 << "  "
                   << std::setw(6) << svc.bus << "  "
                 << std::setw(14) << bus_name(data, svc.bus) << "  "
                   << std::setw(8) << svc.control_bus << "  "
                   << std::setw(5) << (svc.mode == 1 ? "I" : "P") << "  "
                 << std::setw(11) << voltage << "  "
                 << std::setw(10) << vref << "  "
                 << std::setw(10) << svc.slope * 100.0 << "  "
                   << std::setw(13) << qsvc << "  "
                 << std::setw(13) << qinit << "  "
                 << std::setw(13) << clean_output_zero(qsvc - qinit) << "  "
                   << std::setw(12) << svc.qmin_mvar << "  "
                   << std::setw(12) << svc.qmax_mvar << "  "
                 << std::setw(9) << svc_limit_label(state) << "  "
                 << std::setw(12) << residual << "\n";
        }
    }

    write_csc_results(output, data, result);
    write_ltc_results(output, data, result);
    write_pst_results(output, data, result);
    write_lcc_results(output, data, result);
    write_mismatch_diagnostics(output, data, result);

    output << "\nPYOMO_WARM_START_BEGIN\n";
    output << std::setprecision(17);
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        const bool at_voltage_limit = data.buses[i].type == BusType::PQ &&
            (std::abs(result.vm[i] - data.buses[i].vmin) <= TOLERANCE ||
             std::abs(result.vm[i] - data.buses[i].vmax) <= TOLERANCE);
        const int vlim = (i < result.vlim_controlled.size() && result.vlim_controlled[i] != 0) || at_voltage_limit ? 1 : 0;
         const double pg_mw = result.p_calc[i] * data.base_mva + data.buses[i].pl_mw;
         const double qg_mvar = result.q_calc[i] * data.base_mva + data.buses[i].ql_mvar;
        output << "BUS " << data.buses[i].id << " " << result.vm[i] << " " << result.va[i]
             << " " << vlim << " " << pg_mw << " " << qg_mvar
             << " " << data.buses[i].gsh << " " << data.buses[i].bsh << "\n";
    }
    for (const Branch& branch : data.branches) {
        output << "BRANCH " << branch.from << " " << branch.to << " " << branch.circuit
               << " " << branch.r << " " << branch.x << " " << branch.b
               << " " << branch.tap << " " << branch.phase_rad << "\n";
    }
    for (const BusShunt& shunt : data.bus_shunts) {
        output << "SHUNT " << shunt.bus << " " << shunt.owner_bus << " " << shunt.remote_bus
               << " " << shunt.applied_q_mvar << "\n";
    }
    for (const Ltc& ltc : data.ltcs) {
        output << "LTC " << ltc.from << " " << ltc.to << " " << ltc.circuit
               << " " << ltc.control_bus << " " << ltc.tap << "\n";
    }
    for (std::size_t i = 0; i < data.svcs.size(); ++i) {
        const double q_mvar = i < result.svc_q_mvar.size() ? result.svc_q_mvar[i] : data.svcs[i].q_mvar;
        output << "SVC " << data.svcs[i].bus << " " << data.svcs[i].control_bus
               << " " << q_mvar << "\n";
    }
    for (const Lcc& lcc : data.lccs) {
        output << "LCC " << lcc.rectifier_bus << " " << lcc.inverter_bus
               << " " << lcc.p_rectifier_mw << " " << lcc.p_inverter_mw
               << " " << lcc.q_rectifier_mvar << " " << lcc.q_inverter_mvar << "\n";
    }
    output << "PYOMO_WARM_START_END\n";

    output << "\nBranch flows and losses\n";
    output << std::right
           << std::setw(6) << "Branch" << "  "
           << std::setw(6) << "From" << "  "
           << std::setw(6) << "To" << "  "
           << std::setw(14) << "P_from(MW)" << "  "
           << std::setw(14) << "Q_from(MVAr)" << "  "
           << std::setw(12) << "P_to(MW)" << "  "
           << std::setw(13) << "Q_to(MVAr)" << "  "
           << std::setw(10) << "Rate(MVA)" << "  "
           << std::setw(10) << "Loading%" << "  "
           << std::setw(13) << "P_loss(MW)" << "  "
           << std::setw(15) << "Q_loss(MVAr)" << "  "
           << std::setw(9) << "Violation" << "\n";
    output << std::string(145, '-') << "\n";
    for (std::size_t i = 0; i < data.branches.size(); ++i) {
        const Branch& branch = data.branches[i];
        const BranchFlow& flow = branch_flows[i];
        output << std::setw(6) << i + 1 << "  "
               << std::setw(6) << branch.from << "  "
               << std::setw(6) << branch.to << "  "
               << std::setw(14) << flow.p_from_mw << "  "
               << std::setw(14) << flow.q_from_mvar << "  "
               << std::setw(12) << flow.p_to_mw << "  "
               << std::setw(13) << flow.q_to_mvar << "  "
               << std::setw(10) << branch.rate_mva << "  "
               << std::setw(10) << flow.loading_percent << "  "
               << std::setw(13) << flow.p_loss_mw << "  "
               << std::setw(15) << flow.q_loss_mvar << "  "
               << std::setw(9) << (flow.overloaded ? "true" : "false") << "\n";
    }
}
