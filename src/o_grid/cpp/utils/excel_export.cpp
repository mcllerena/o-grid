#include "../headers/utils/excel_export.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <stdexcept>
#include <utility>

#include "../headers/models/csc.h"
#include "../headers/utils/branch_flow.h"
#include "../headers/utils/reporting.h"

namespace {

struct ExcelCell {
    enum class Type {
        Blank,
        Text,
        Number,
        Boolean,
    };

    Type type = Type::Blank;
    std::string text;
    double number = 0.0;
    bool boolean = false;
    bool fixed_decimal = false;
};

using ExcelRow = std::vector<ExcelCell>;
using ExcelRows = std::vector<ExcelRow>;

struct ExcelSheet {
    std::string name;
    ExcelRows rows;
};

struct ZipEntry {
    std::string path;
    std::string content;
    std::uint32_t crc = 0;
    std::uint32_t local_header_offset = 0;
};

ExcelCell text_cell(const std::string& value) {
    ExcelCell cell;
    cell.type = ExcelCell::Type::Text;
    cell.text = value;
    return cell;
}

ExcelCell text_cell(const char* value) {
    return text_cell(std::string(value));
}

ExcelCell number_cell(double value) {
    ExcelCell cell;
    cell.type = ExcelCell::Type::Number;
    cell.number = clean_output_zero(value);
    cell.fixed_decimal = true;
    return cell;
}

ExcelCell optional_number_cell(double value, bool has_value) {
    return has_value ? number_cell(value) : ExcelCell{};
}

ExcelCell int_cell(int value) {
    ExcelCell cell;
    cell.type = ExcelCell::Type::Number;
    cell.number = static_cast<double>(value);
    return cell;
}

ExcelCell size_cell(std::size_t value) {
    ExcelCell cell;
    cell.type = ExcelCell::Type::Number;
    cell.number = static_cast<double>(value);
    return cell;
}

ExcelCell bool_cell(bool value) {
    ExcelCell cell;
    cell.type = ExcelCell::Type::Boolean;
    cell.boolean = value;
    return cell;
}

std::string xml_escape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (char character : value) {
        switch (character) {
        case '&':
            escaped += "&amp;";
            break;
        case '<':
            escaped += "&lt;";
            break;
        case '>':
            escaped += "&gt;";
            break;
        case '"':
            escaped += "&quot;";
            break;
        default:
            if (static_cast<unsigned char>(character) >= 0x20 || character == '\n' || character == '\r' || character == '\t') {
                escaped += character;
            }
            break;
        }
    }
    return escaped;
}

std::string number_to_string(double value) {
    std::ostringstream stream;
    stream << std::setprecision(15) << clean_output_zero(value);
    return stream.str();
}

std::string excel_column_name(std::size_t column_index) {
    std::string name;
    std::size_t value = column_index + 1;
    while (value > 0) {
        const std::size_t remainder = (value - 1) % 26;
        name.insert(name.begin(), static_cast<char>('A' + remainder));
        value = (value - 1) / 26;
    }
    return name;
}

std::string bus_type_name(BusType type) {
    if (type == BusType::Slack) {
        return "Slack";
    }
    if (type == BusType::PV) {
        return "PV";
    }
    return "PQ";
}

std::string bus_type_name(const Bus& bus) {
    if (bus.zero_generation_voltage_control) {
        return "-1";
    }
    return bus_type_name(bus.type);
}

std::string svc_limit_label(int state) {
    if (state > 0) {
        return "Qmax";
    }
    if (state < 0) {
        return "Qmin";
    }
    return "Free";
}

double bus_voltage(const CaseData& data, const PowerFlowResult& result, int bus_id) {
    for (std::size_t bus_index = 0; bus_index < data.buses.size() && bus_index < result.vm.size(); ++bus_index) {
        if (data.buses[bus_index].id == bus_id) {
            return result.vm[bus_index];
        }
    }
    return 1.0;
}

double commutation_angle_deg(double angle_deg,
                             double pdc_mw,
                             double vdc_kv,
                             double commutating_reactance,
                             double tap,
                             double terminal_voltage_kv) {
    if (std::abs(vdc_kv) <= TOLERANCE || commutating_reactance <= TOLERANCE || tap <= TOLERANCE || terminal_voltage_kv <= TOLERANCE) {
        return 0.0;
    }
    const double dc_current_ka = std::abs(pdc_mw / vdc_kv);
    if (dc_current_ka <= TOLERANCE) {
        return 0.0;
    }
    const double angle_rad = angle_deg * kPi / 180.0;
    const double acos_argument = std::cos(angle_rad) - std::sqrt(2.0) * commutating_reactance * dc_current_ka /
        (tap * terminal_voltage_kv);
    const double clamped_argument = std::max(-1.0, std::min(1.0, acos_argument));
    return (std::acos(clamped_argument) - angle_rad) * 180.0 / kPi;
}

double rectifier_commutation_angle_deg(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    if (lcc.mu_rectifier_deg > 0.0 || std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return lcc.mu_rectifier_deg;
    }
    const double terminal_voltage_kv = bus_voltage(data, result, lcc.rectifier_bus) * lcc.rectifier_bridge_voltage_kv;
    return commutation_angle_deg(lcc.alpha_deg, lcc.pdc_mw, lcc.vdc_rectifier_kv, lcc.xcr, lcc.tap_rectifier, terminal_voltage_kv);
}

double inverter_commutation_angle_deg(const Lcc& lcc, const CaseData& data, const PowerFlowResult& result) {
    if (lcc.mu_inverter_deg > 0.0 || std::abs(lcc.pdc_mw) <= TOLERANCE) {
        return lcc.mu_inverter_deg;
    }
    const double terminal_voltage_kv = bus_voltage(data, result, lcc.inverter_bus) * lcc.inverter_bridge_voltage_kv;
    return commutation_angle_deg(lcc.gamma_deg, lcc.pdc_mw, lcc.vdc_inverter_kv, lcc.xci, lcc.tap_inverter, terminal_voltage_kv);
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

ExcelRows summary_rows(const std::string& case_path,
                       const std::string& output_path,
                       const CaseData& data,
                       const PowerFlowResult& result,
                       const std::vector<BranchFlow>& branch_flows) {
    const ViolationSummary violations = make_violation_summary(data, result, branch_flows);
    return {
        {text_cell("Field"), text_cell("Value")},
        {text_cell("Case"), text_cell(case_path)},
        {text_cell("Workbook"), text_cell(output_path)},
        {text_cell("Converged"), bool_cell(result.converged)},
        {text_cell("Iterations"), int_cell(result.iterations)},
        {text_cell("Max Mismatch (pu)"), number_cell(result.max_mismatch)},
        {text_cell("Base MVA"), number_cell(data.base_mva)},
        {text_cell("Buses"), size_cell(data.buses.size())},
        {text_cell("Generators"), int_cell(count_generator_buses(data))},
        {text_cell("Loads"), int_cell(count_load_buses(data))},
        {text_cell("Lines"), size_cell(data.branches.size())},
        {text_cell("LTC"), size_cell(data.ltcs.size())},
        {text_cell("PST"), size_cell(data.psts.size())},
        {text_cell("HVDC"), size_cell(data.lccs.size())},
        {text_cell("SVC"), size_cell(data.svcs.size())},
        {text_cell("CSC"), size_cell(data.cscs.size())},
        {text_cell("Voltage Upper Violations"), int_cell(violations.voltage_upper)},
        {text_cell("Voltage Lower Violations"), int_cell(violations.voltage_lower)},
        {text_cell("Line Flow Overloads"), int_cell(violations.line_overloads)},
    };
}

ExcelRows bus_rows(const CaseData& data, const PowerFlowResult& result) {
    ExcelRows rows;
    rows.push_back({text_cell("Bus"), text_cell("Name"), text_cell("Type"), text_cell("Area"), text_cell("InServ"),
                    text_cell("Vm(pu)"), text_cell("Vm(kV)"), text_cell("Va(deg)"),
                    text_cell("Pg(MW)"), text_cell("Qg(MVAr)"), text_cell("Pl(MW)"), text_cell("Ql(MVAr)"),
                    text_cell("Vmin"), text_cell("Vmax"), text_cell("Violation"), text_cell("RepresentativeBus"),
                    text_cell("Collapsed")});
    std::map<int, std::size_t> solved_bus_index;
    for (std::size_t bus_index = 0; bus_index < data.buses.size(); ++bus_index) {
        solved_bus_index[data.buses[bus_index].id] = bus_index;
    }

    if (!data.original_buses.empty()) {
        for (const OriginalBusRecord& original_bus : data.original_buses) {
            const Bus& bus = original_bus.bus;
            const auto solved_it = solved_bus_index.find(original_bus.representative_bus);
            const bool has_solved_result = original_bus.in_service && solved_it != solved_bus_index.end();
            const std::size_t solved_index = has_solved_result ? solved_it->second : 0;
            const double vm = has_solved_result && solved_index < result.vm.size() ? result.vm[solved_index] : bus.voltage;
            const double va = has_solved_result && solved_index < result.va.size() ? result.va[solved_index] * 180.0 / kPi : bus.angle_rad * 180.0 / kPi;
            const double pg_mw = has_solved_result && !original_bus.collapsed && solved_index < result.p_calc.size()
                ? result.p_calc[solved_index] * data.base_mva + bus.pl_mw
                : bus.pg_mw;
            const double qg_mvar = has_solved_result && !original_bus.collapsed && solved_index < result.q_calc.size()
                ? result.q_calc[solved_index] * data.base_mva + bus.ql_mvar
                : bus.qg_mvar;
            rows.push_back({int_cell(bus.id), text_cell(bus.name), text_cell(bus_type_name(bus)), int_cell(bus.area), bool_cell(original_bus.in_service),
                            number_cell(vm), optional_number_cell(vm * bus.base_kv, bus.base_kv > 0.0), number_cell(va),
                            number_cell(pg_mw), number_cell(qg_mvar), number_cell(bus.pl_mw), number_cell(bus.ql_mvar),
                            number_cell(bus.vmin), number_cell(bus.vmax), text_cell(original_bus.in_service ? voltage_violation_label(bus, vm) : "disabled"),
                            original_bus.in_service ? int_cell(original_bus.representative_bus) : text_cell(""),
                            bool_cell(original_bus.collapsed)});
        }
        return rows;
    }

    for (std::size_t bus_index = 0; bus_index < data.buses.size(); ++bus_index) {
        const Bus& bus = data.buses[bus_index];
        const double vm = bus_index < result.vm.size() ? result.vm[bus_index] : bus.voltage;
        const double va = bus_index < result.va.size() ? result.va[bus_index] * 180.0 / kPi : bus.angle_rad * 180.0 / kPi;
        const double pg_mw = bus_index < result.p_calc.size() ? result.p_calc[bus_index] * data.base_mva + bus.pl_mw : bus.pg_mw;
        const double qg_mvar = bus_index < result.q_calc.size() ? result.q_calc[bus_index] * data.base_mva + bus.ql_mvar : bus.qg_mvar;
        rows.push_back({int_cell(bus.id), text_cell(bus.name), text_cell(bus_type_name(bus)), int_cell(bus.area), bool_cell(bus.in_service),
                number_cell(vm), optional_number_cell(vm * bus.base_kv, bus.base_kv > 0.0), number_cell(va),
                        number_cell(pg_mw), number_cell(qg_mvar), number_cell(bus.pl_mw), number_cell(bus.ql_mvar),
                        number_cell(bus.vmin), number_cell(bus.vmax), text_cell(voltage_violation_label(bus, vm)),
                int_cell(bus.id), bool_cell(false)});
    }
    return rows;
}

ExcelRows generator_rows(const CaseData& data, const PowerFlowResult& result) {
    ExcelRows rows;
    rows.push_back({text_cell("Bus"), text_cell("Name"), text_cell("Type"), text_cell("Pg(MW)"), text_cell("Qg(MVAr)"),
                    text_cell("Vm(pu)"), text_cell("Va(deg)")});
    for (std::size_t bus_index = 0; bus_index < data.buses.size(); ++bus_index) {
        const Bus& bus = data.buses[bus_index];
        const bool generator_bus = std::abs(bus.pg_mw) > DISPLAY_TOLERANCE || std::abs(bus.qg_mvar) > DISPLAY_TOLERANCE ||
            bus.type == BusType::PV || bus.type == BusType::Slack;
        if (!generator_bus) {
            continue;
        }
        const double vm = bus_index < result.vm.size() ? result.vm[bus_index] : bus.voltage;
        const double va = bus_index < result.va.size() ? result.va[bus_index] * 180.0 / kPi : bus.angle_rad * 180.0 / kPi;
        const double pg_mw = bus_index < result.p_calc.size() ? result.p_calc[bus_index] * data.base_mva + bus.pl_mw : bus.pg_mw;
        const double qg_mvar = bus_index < result.q_calc.size() ? result.q_calc[bus_index] * data.base_mva + bus.ql_mvar : bus.qg_mvar;
        rows.push_back({int_cell(bus.id), text_cell(bus.name), text_cell(bus_type_name(bus)), number_cell(pg_mw),
                        number_cell(qg_mvar), number_cell(vm), number_cell(va)});
    }
    return rows;
}

ExcelRows load_rows(const CaseData& data) {
    ExcelRows rows;
    rows.push_back({text_cell("Bus"), text_cell("Name"), text_cell("Pl(MW)"), text_cell("Ql(MVAr)"), text_cell("Source")});
    std::map<int, std::string> names_by_bus;
    for (const Bus& bus : data.buses) {
        names_by_bus[bus.id] = bus.name;
        if (std::abs(bus.pl_mw) > DISPLAY_TOLERANCE || std::abs(bus.ql_mvar) > DISPLAY_TOLERANCE) {
            rows.push_back({int_cell(bus.id), text_cell(bus.name), number_cell(bus.pl_mw), number_cell(bus.ql_mvar), text_cell("Bus")});
        }
    }
    for (const IndividualLoad& load : data.individual_loads) {
        rows.push_back({int_cell(load.bus), text_cell(names_by_bus[load.bus]), number_cell(load.p_mw), number_cell(load.q_mvar), text_cell("Individual")});
    }
    return rows;
}

ExcelRows line_rows(const CaseData& data, const std::vector<BranchFlow>& branch_flows) {
    ExcelRows rows;
    rows.push_back({text_cell("Line"), text_cell("From"), text_cell("To"), text_cell("Circuit"), text_cell("R(pu)"), text_cell("X(pu)"),
                    text_cell("B(pu)"), text_cell("Tap"), text_cell("Shift(deg)"), text_cell("Rate(MVA)"), text_cell("Pfrom(MW)"),
                    text_cell("Qfrom(MVAr)"), text_cell("Pto(MW)"), text_cell("Qto(MVAr)"), text_cell("Loading%"),
                    text_cell("P_loss(MW)"), text_cell("Q_loss(MVAr)"), text_cell("Violation")});
    for (std::size_t branch_index = 0; branch_index < data.branches.size(); ++branch_index) {
        const Branch& branch = data.branches[branch_index];
        const BranchFlow flow = branch_index < branch_flows.size() ? branch_flows[branch_index] : BranchFlow{};
        rows.push_back({size_cell(branch_index + 1), int_cell(branch.from), int_cell(branch.to), int_cell(branch.circuit), number_cell(branch.r),
                        number_cell(branch.x), number_cell(branch.b), number_cell(branch.tap), number_cell(branch.phase_rad * 180.0 / kPi),
                        number_cell(branch.rate_mva), number_cell(flow.p_from_mw), number_cell(flow.q_from_mvar), number_cell(flow.p_to_mw),
                        number_cell(flow.q_to_mvar), number_cell(flow.loading_percent), number_cell(flow.p_loss_mw), number_cell(flow.q_loss_mvar),
                        text_cell(flow.overloaded ? "true" : "false")});
    }
    return rows;
}

ExcelRows ltc_rows(const CaseData& data, const std::vector<BranchFlow>& branch_flows) {
    ExcelRows rows;
    rows.push_back({text_cell("Device"), text_cell("From"), text_cell("To"), text_cell("Circuit"), text_cell("CtrlBus"), text_cell("Tap"),
                    text_cell("TapMin"), text_cell("TapMax"), text_cell("Vtarget"), text_cell("Pfrom(MW)"), text_cell("Qfrom(MVAr)"),
                    text_cell("Pto(MW)"), text_cell("Qto(MVAr)")});
    for (std::size_t device_index = 0; device_index < data.ltcs.size(); ++device_index) {
        const Ltc& ltc = data.ltcs[device_index];
        BranchFlow flow;
        if (ltc.branch_index >= 0 && static_cast<std::size_t>(ltc.branch_index) < branch_flows.size()) {
            flow = branch_flows[static_cast<std::size_t>(ltc.branch_index)];
        }
        rows.push_back({size_cell(device_index + 1), int_cell(ltc.from), int_cell(ltc.to), int_cell(ltc.circuit), int_cell(ltc.control_bus),
                        number_cell(ltc.tap), number_cell(ltc.tap_min), number_cell(ltc.tap_max), number_cell(ltc.v_target),
                        number_cell(flow.p_from_mw), number_cell(flow.q_from_mvar), number_cell(flow.p_to_mw), number_cell(flow.q_to_mvar)});
    }
    return rows;
}

ExcelRows pst_rows(const CaseData& data, const std::vector<BranchFlow>& branch_flows) {
    ExcelRows rows;
    rows.push_back({text_cell("Device"), text_cell("From"), text_cell("To"), text_cell("Circuit"), text_cell("CtrlBus"), text_cell("Shift(deg)"),
                    text_cell("ShiftMin(deg)"), text_cell("ShiftMax(deg)"), text_cell("Ptarget(MW)"), text_cell("Pfrom(MW)"),
                    text_cell("Qfrom(MVAr)"), text_cell("Pto(MW)"), text_cell("Qto(MVAr)")});
    for (std::size_t device_index = 0; device_index < data.psts.size(); ++device_index) {
        const Pst& pst = data.psts[device_index];
        BranchFlow flow;
        if (pst.branch_index >= 0 && static_cast<std::size_t>(pst.branch_index) < branch_flows.size()) {
            flow = branch_flows[static_cast<std::size_t>(pst.branch_index)];
        }
        rows.push_back({size_cell(device_index + 1), int_cell(pst.from), int_cell(pst.to), int_cell(pst.circuit), int_cell(pst.control_bus),
                        number_cell(pst.phase_rad * 180.0 / kPi), number_cell(pst.phase_min_rad * 180.0 / kPi),
                        number_cell(pst.phase_max_rad * 180.0 / kPi), number_cell(pst.p_target_mw), number_cell(flow.p_from_mw),
                        number_cell(flow.q_from_mvar), number_cell(flow.p_to_mw), number_cell(flow.q_to_mvar)});
    }
    return rows;
}

ExcelRows hvdc_rows(const CaseData& data, const PowerFlowResult& result) {
    ExcelRows rows;
    rows.push_back({text_cell("Bus#"), text_cell("BusName"), text_cell("Volt(pu)"), text_cell("Type"), text_cell("Pole#"),
                    text_cell("Control"), text_cell("P(MW)"), text_cell("Q(MVAr)"), text_cell("Loss(MW)"), text_cell("Vdc(kV)"),
                    text_cell("Idc(pu)"), text_cell("Idc(A)"), text_cell("Alpha(deg)"), text_cell("Mu(deg)"), text_cell("Phi(deg)"),
                    text_cell("Tap"), text_cell("Status")});
    const std::vector<std::size_t> order = lcc_output_order(data);
    for (std::size_t order_index = 0; order_index < order.size(); ++order_index) {
        const std::size_t link_index = order[order_index];
        const Lcc& lcc = data.lccs[link_index];
        const double loss_mw = lcc_dc_loss_mw(lcc);
        const double idc_pu = lcc_idc_pu(lcc);
        const double inverter_p_mw = -lcc.p_inverter_mw;
        const std::string status = std::abs(lcc.pdc_mw) > TOLERANCE ? "ON" : "OFF";
        const int pole = lcc_pole_number(lcc, link_index);
        rows.push_back({int_cell(lcc.rectifier_bus), text_cell(bus_name(data, lcc.rectifier_bus)), number_cell(lcc_rectifier_dc_voltage_pu(lcc)),
                        text_cell("Rectifier"), int_cell(pole), text_cell("Power"), number_cell(lcc.p_rectifier_mw), number_cell(lcc.q_rectifier_mvar),
                        number_cell(loss_mw), number_cell(lcc.vdc_rectifier_kv), number_cell(idc_pu), number_cell(lcc.idc_a), number_cell(lcc.alpha_deg),
                        number_cell(rectifier_commutation_angle_deg(lcc, data, result)), text_cell("-"), number_cell(lcc_report_tap_rectifier(lcc, data, result)),
                        text_cell(status)});
        rows.push_back({int_cell(lcc.inverter_bus), text_cell(bus_name(data, lcc.inverter_bus)), number_cell(lcc_inverter_dc_voltage_pu(lcc)),
                        text_cell("Inverter"), int_cell(pole), text_cell("-"), number_cell(inverter_p_mw), number_cell(lcc.q_inverter_mvar),
                        number_cell(loss_mw), number_cell(lcc.vdc_inverter_kv), number_cell(-idc_pu), number_cell(-lcc.idc_a), number_cell(lcc.gamma_deg),
                        number_cell(inverter_commutation_angle_deg(lcc, data, result)), text_cell("-"), number_cell(lcc_report_tap_inverter(lcc, data, result)),
                        text_cell(status)});
    }
    return rows;
}

ExcelRows svc_rows(const CaseData& data, const PowerFlowResult& result) {
    ExcelRows rows;
    rows.push_back({text_cell("SVC"), text_cell("Bus"), text_cell("Name"), text_cell("Ctrl Bus"), text_cell("Mode"),
                    text_cell("Voltage(pu)"), text_cell("Vref(pu)"), text_cell("Slope(%)"), text_cell("Qsvc(MVAr)"),
                    text_cell("Qinit(MVAr)"), text_cell("DeltaQ(MVAr)"), text_cell("Qmin(MVAr)"), text_cell("Qmax(MVAr)"),
                    text_cell("Status"), text_cell("EqResidual")});
    for (std::size_t device_index = 0; device_index < data.svcs.size(); ++device_index) {
        const Svc& svc = data.svcs[device_index];
        const double qsvc = device_index < result.svc_q_mvar.size() ? result.svc_q_mvar[device_index] : 0.0;
        const double qinit = device_index < result.svc_q_initial_mvar.size() ? result.svc_q_initial_mvar[device_index] : svc.q_mvar;
        const double voltage = device_index < result.svc_v_control_pu.size() ? result.svc_v_control_pu[device_index] : 0.0;
        const double vref = device_index < result.svc_v_ref_pu.size() ? result.svc_v_ref_pu[device_index] : 0.0;
        const double residual = device_index < result.svc_control_residual.size() ? result.svc_control_residual[device_index] : 0.0;
        const int state = device_index < result.svc_state.size() ? result.svc_state[device_index] : 0;
        rows.push_back({size_cell(device_index + 1), int_cell(svc.bus), text_cell(bus_name(data, svc.bus)), int_cell(svc.control_bus),
                        text_cell(svc.mode == 1 ? "I" : "P"), number_cell(voltage), number_cell(vref), number_cell(svc.slope * 100.0),
                        number_cell(qsvc), number_cell(qinit), number_cell(qsvc - qinit), number_cell(svc.qmin_mvar),
                        number_cell(svc.qmax_mvar), text_cell(svc_limit_label(state)), number_cell(residual)});
    }
    return rows;
}

ExcelRows csc_rows(const CaseData& data, const PowerFlowResult& result) {
    ExcelRows rows;
    rows.push_back({text_cell("Device"), text_cell("From"), text_cell("To"), text_cell("Circuit"), text_cell("Mode"), text_cell("X(pu)"),
                    text_cell("Xmin(pu)"), text_cell("Xmax(pu)"), text_cell("Pfrom(MW)"), text_cell("Qfrom(MVAr)"),
                    text_cell("Pto(MW)"), text_cell("Qto(MVAr)"), text_cell("Status")});
    const std::vector<CscFlow> flows = calculate_csc_flows(data, result.vm, result.va);
    std::map<int, CscFlow> flow_by_device;
    for (const CscFlow& flow : flows) {
        flow_by_device[flow.device_index] = flow;
    }
    for (std::size_t device_index = 0; device_index < data.cscs.size(); ++device_index) {
        const Csc& csc = data.cscs[device_index];
        const auto flow_it = flow_by_device.find(static_cast<int>(device_index));
        const bool in_service = flow_it != flow_by_device.end();
        const CscFlow flow = in_service ? flow_it->second : CscFlow{};
        rows.push_back({size_cell(device_index + 1), int_cell(csc.from), int_cell(csc.to), int_cell(csc.circuit), text_cell(csc.mode),
                        number_cell(csc.x_pu), number_cell(csc.xmin_pu), number_cell(csc.xmax_pu), number_cell(flow.p_from_mw),
                        number_cell(flow.q_from_mvar), number_cell(flow.p_to_mw), number_cell(flow.q_to_mvar), text_cell(in_service ? "InSvc" : "Bypass")});
    }
    return rows;
}

std::uint32_t crc32(const std::string& content) {
    std::uint32_t crc = 0xFFFFFFFFu;
    for (unsigned char byte : content) {
        crc ^= byte;
        for (int bit_index = 0; bit_index < 8; ++bit_index) {
            const std::uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1u) ^ (0xEDB88320u & mask);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

void write_u16(std::ostream& output, std::uint16_t value) {
    output.put(static_cast<char>(value & 0xFFu));
    output.put(static_cast<char>((value >> 8u) & 0xFFu));
}

void write_u32(std::ostream& output, std::uint32_t value) {
    output.put(static_cast<char>(value & 0xFFu));
    output.put(static_cast<char>((value >> 8u) & 0xFFu));
    output.put(static_cast<char>((value >> 16u) & 0xFFu));
    output.put(static_cast<char>((value >> 24u) & 0xFFu));
}

void write_zip(const std::filesystem::path& path, std::vector<ZipEntry> entries) {
    std::ofstream output(path, std::ios::binary);
    if (!output) {
        throw std::runtime_error("Could not write Excel file: " + path.string());
    }

    for (ZipEntry& entry : entries) {
        entry.crc = crc32(entry.content);
        entry.local_header_offset = static_cast<std::uint32_t>(output.tellp());
        write_u32(output, 0x04034b50u);
        write_u16(output, 20);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u32(output, entry.crc);
        write_u32(output, static_cast<std::uint32_t>(entry.content.size()));
        write_u32(output, static_cast<std::uint32_t>(entry.content.size()));
        write_u16(output, static_cast<std::uint16_t>(entry.path.size()));
        write_u16(output, 0);
        output.write(entry.path.data(), static_cast<std::streamsize>(entry.path.size()));
        output.write(entry.content.data(), static_cast<std::streamsize>(entry.content.size()));
    }

    const std::uint32_t central_directory_offset = static_cast<std::uint32_t>(output.tellp());
    for (const ZipEntry& entry : entries) {
        write_u32(output, 0x02014b50u);
        write_u16(output, 20);
        write_u16(output, 20);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u32(output, entry.crc);
        write_u32(output, static_cast<std::uint32_t>(entry.content.size()));
        write_u32(output, static_cast<std::uint32_t>(entry.content.size()));
        write_u16(output, static_cast<std::uint16_t>(entry.path.size()));
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u16(output, 0);
        write_u32(output, 0);
        write_u32(output, entry.local_header_offset);
        output.write(entry.path.data(), static_cast<std::streamsize>(entry.path.size()));
    }
    const std::uint32_t central_directory_size = static_cast<std::uint32_t>(output.tellp()) - central_directory_offset;

    write_u32(output, 0x06054b50u);
    write_u16(output, 0);
    write_u16(output, 0);
    write_u16(output, static_cast<std::uint16_t>(entries.size()));
    write_u16(output, static_cast<std::uint16_t>(entries.size()));
    write_u32(output, central_directory_size);
    write_u32(output, central_directory_offset);
    write_u16(output, 0);
}

std::string worksheet_xml(const ExcelRows& rows) {
    std::ostringstream xml;
    xml << "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";
    xml << "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">";
    xml << "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/></sheetView></sheetViews>";
    xml << "<sheetData>";
    for (std::size_t row_index = 0; row_index < rows.size(); ++row_index) {
        xml << "<row r=\"" << row_index + 1 << "\">";
        for (std::size_t column_index = 0; column_index < rows[row_index].size(); ++column_index) {
            const ExcelCell& cell = rows[row_index][column_index];
            const std::string reference = excel_column_name(column_index) + std::to_string(row_index + 1);
            if (cell.type == ExcelCell::Type::Blank) {
                xml << "<c r=\"" << reference << "\"/>";
            } else if (cell.type == ExcelCell::Type::Text) {
                xml << "<c r=\"" << reference << "\" t=\"inlineStr\"><is><t>" << xml_escape(cell.text) << "</t></is></c>";
            } else if (cell.type == ExcelCell::Type::Boolean) {
                xml << "<c r=\"" << reference << "\" t=\"b\"><v>" << (cell.boolean ? 1 : 0) << "</v></c>";
            } else {
                xml << "<c r=\"" << reference << "\"";
                if (cell.fixed_decimal) {
                    xml << " s=\"1\"";
                }
                xml << "><v>" << number_to_string(cell.number) << "</v></c>";
            }
        }
        xml << "</row>";
    }
    xml << "</sheetData></worksheet>";
    return xml.str();
}

std::string content_types_xml(std::size_t sheet_count) {
    std::ostringstream xml;
    xml << "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";
    xml << "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">";
    xml << "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>";
    xml << "<Default Extension=\"xml\" ContentType=\"application/xml\"/>";
    xml << "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>";
    xml << "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>";
    for (std::size_t sheet_index = 0; sheet_index < sheet_count; ++sheet_index) {
        xml << "<Override PartName=\"/xl/worksheets/sheet" << sheet_index + 1
            << ".xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>";
    }
    xml << "</Types>";
    return xml.str();
}

std::string root_relationships_xml() {
    return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "</Relationships>";
}

std::string workbook_xml(const std::vector<ExcelSheet>& sheets) {
    std::ostringstream xml;
    xml << "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";
    xml << "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">";
    xml << "<sheets>";
    for (std::size_t sheet_index = 0; sheet_index < sheets.size(); ++sheet_index) {
        xml << "<sheet name=\"" << xml_escape(sheets[sheet_index].name) << "\" sheetId=\"" << sheet_index + 1
            << "\" r:id=\"rId" << sheet_index + 1 << "\"/>";
    }
    xml << "</sheets></workbook>";
    return xml.str();
}

std::string workbook_relationships_xml(const std::vector<ExcelSheet>& sheets) {
    std::ostringstream xml;
    xml << "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";
    xml << "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">";
    for (std::size_t sheet_index = 0; sheet_index < sheets.size(); ++sheet_index) {
        xml << "<Relationship Id=\"rId" << sheet_index + 1
            << "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet"
            << sheet_index + 1 << ".xml\"/>";
    }
    xml << "<Relationship Id=\"rId" << sheets.size() + 1
        << "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>";
    xml << "</Relationships>";
    return xml.str();
}

std::string styles_xml() {
    return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
    "<numFmts count=\"1\"><numFmt numFmtId=\"164\" formatCode=\"0.0000\"/></numFmts>"
        "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
        "<fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>"
        "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
    "<cellXfs count=\"2\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>"
    "<xf numFmtId=\"164\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyNumberFormat=\"1\"/></cellXfs>"
        "<cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>"
        "<dxfs count=\"0\"/>"
        "<tableStyles count=\"0\" defaultTableStyle=\"TableStyleMedium9\" defaultPivotStyle=\"PivotStyleLight16\"/>"
        "</styleSheet>";
}

void write_xlsx(const std::filesystem::path& path, const std::vector<ExcelSheet>& sheets) {
    std::vector<ZipEntry> entries;
    entries.push_back({"[Content_Types].xml", content_types_xml(sheets.size())});
    entries.push_back({"_rels/.rels", root_relationships_xml()});
    entries.push_back({"xl/workbook.xml", workbook_xml(sheets)});
    entries.push_back({"xl/_rels/workbook.xml.rels", workbook_relationships_xml(sheets)});
    entries.push_back({"xl/styles.xml", styles_xml()});
    for (std::size_t sheet_index = 0; sheet_index < sheets.size(); ++sheet_index) {
        entries.push_back({"xl/worksheets/sheet" + std::to_string(sheet_index + 1) + ".xml", worksheet_xml(sheets[sheet_index].rows)});
    }
    write_zip(path, std::move(entries));
}

std::filesystem::path case_root_path(const std::string& case_path) {
    const std::filesystem::path input_path(case_path);
    const std::filesystem::path parent = input_path.parent_path();
    if (parent.filename().string() == "data") {
        const std::filesystem::path root = parent.parent_path();
        return root.empty() ? std::filesystem::path(".") : root;
    }
    return parent.empty() ? std::filesystem::path(".") : parent;
}

std::string results_suffix(const std::string& algorithm_suffix) {
    return algorithm_suffix.empty() ? "_results" : "_results_" + algorithm_suffix;
}

std::filesystem::path append_results_suffix(const std::filesystem::path& output_path, const std::string& algorithm_suffix) {
    const std::string suffix = results_suffix(algorithm_suffix);
    const std::string stem = output_path.stem().string();
    if (stem.size() >= suffix.size() && stem.compare(stem.size() - suffix.size(), suffix.size(), suffix) == 0) {
        return output_path;
    }
    return output_path.parent_path() / (stem + suffix + output_path.extension().string());
}

std::filesystem::path resolve_excel_path_impl(const std::string& case_path, const std::string& destination, const std::string& algorithm_suffix) {
    const std::filesystem::path input_path(case_path);
    const std::string stem = input_path.stem().string();
    const std::string suffix = results_suffix(algorithm_suffix);
    if (!destination.empty()) {
        std::filesystem::path output_path(destination);
        if (output_path.extension() == ".xlsx") {
            return append_results_suffix(output_path, algorithm_suffix);
        }
        output_path /= stem + suffix + ".xlsx";
        return output_path;
    }
    return case_root_path(case_path) / "results" / (stem + suffix + ".xlsx");
}

} // namespace

std::string default_excel_results_path(const std::string& case_path, const std::string& algorithm_suffix) {
    return resolve_excel_path_impl(case_path, "", algorithm_suffix).string();
}

std::string resolve_excel_results_path(const std::string& case_path, const std::string& destination, const std::string& algorithm_suffix) {
    return resolve_excel_path_impl(case_path, destination, algorithm_suffix).string();
}

void export_results_to_excel(const std::string& case_path,
                             const CaseData& data,
                             const PowerFlowResult& result,
                             const std::vector<BranchFlow>& branch_flows,
                             const std::string& destination,
                             const std::string& algorithm_suffix) {
    const std::filesystem::path output_path = resolve_excel_path_impl(case_path, destination, algorithm_suffix);
    if (!output_path.parent_path().empty()) {
        std::filesystem::create_directories(output_path.parent_path());
    }

    const std::vector<ExcelSheet> sheets = {
        {"Summary", summary_rows(case_path, output_path.string(), data, result, branch_flows)},
        {"Buses", bus_rows(data, result)},
        {"Generators", generator_rows(data, result)},
        {"Loads", load_rows(data)},
        {"Lines", line_rows(data, branch_flows)},
        {"LTC", ltc_rows(data, branch_flows)},
        {"PST", pst_rows(data, branch_flows)},
        {"HVDC", hvdc_rows(data, result)},
        {"SVC", svc_rows(data, result)},
        {"CSC", csc_rows(data, result)},
    };
    write_xlsx(output_path, sheets);
}