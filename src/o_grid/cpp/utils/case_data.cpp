#include "../headers/case_data.h"

#include "../headers/models/ltc.h"
#include "../headers/models/pst.h"
#include "../headers/models/shunt.h"
#include "../headers/utils/network_reduction.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

namespace {

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string strip_comment(const std::string& line, char marker) {
    bool in_quote = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        if (line[i] == '"' || line[i] == '\'') {
            in_quote = !in_quote;
        } else if (line[i] == marker && !in_quote) {
            return line.substr(0, i);
        }
    }
    return line;
}

std::vector<std::string> tokenize(const std::string& line) {
    std::vector<std::string> tokens;
    std::string token;
    bool in_quote = false;

    for (char ch : line) {
        if (ch == '"' || ch == '\'') {
            in_quote = !in_quote;
            continue;
        }

        if (std::isspace(static_cast<unsigned char>(ch)) && !in_quote) {
            if (!token.empty()) {
                tokens.push_back(token);
                token.clear();
            }
        } else if ((ch == ';' || ch == '[' || ch == ']') && !in_quote) {
            if (!token.empty()) {
                tokens.push_back(token);
                token.clear();
            }
        } else {
            token.push_back(ch);
        }
    }

    if (!token.empty()) {
        tokens.push_back(token);
    }

    return tokens;
}

double parse_double(const std::string& text, const std::string& field) {
    try {
        std::size_t used = 0;
        const double value = std::stod(text, &used);
        if (used != text.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return value;
    } catch (const std::exception&) {
        throw std::runtime_error("Could not parse " + field + " from '" + text + "'");
    }
}

int parse_int(const std::string& text, const std::string& field) {
    try {
        std::size_t used = 0;
        const int value = std::stoi(text, &used);
        if (used != text.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return value;
    } catch (const std::exception&) {
        throw std::runtime_error("Could not parse " + field + " from '" + text + "'");
    }
}

BusType read_matpower_bus_type(int type) {
    if (type == 1) {
        return BusType::PQ;
    }
    if (type == 2) {
        return BusType::PV;
    }
    if (type == 3) {
        return BusType::Slack;
    }
    throw std::runtime_error("Unsupported MATPOWER bus type: " + std::to_string(type));
}

std::vector<double> numeric_row(const std::string& line) {
    const auto tokens = tokenize(line);
    std::vector<double> row;
    row.reserve(tokens.size());
    for (const std::string& token : tokens) {
        row.push_back(parse_double(token, "matrix value"));
    }
    return row;
}

std::size_t field_index(const std::vector<std::string>& headers,
                        const std::vector<std::string>& aliases,
                        const std::string& context) {
    for (const std::string& alias : aliases) {
        const auto it = std::find(headers.begin(), headers.end(), alias);
        if (it != headers.end()) {
            return static_cast<std::size_t>(std::distance(headers.begin(), it));
        }
    }
    throw std::runtime_error("Missing " + context + " field in section header");
}

bool has_field(const std::vector<std::string>& headers, const std::string& name) {
    return std::find(headers.begin(), headers.end(), name) != headers.end();
}

std::string token_at(const std::vector<std::string>& tokens,
                     const std::vector<std::string>& headers,
                     const std::vector<std::string>& aliases,
                     const std::string& context) {
    const std::size_t index = field_index(headers, aliases, context);
    if (index >= tokens.size()) {
        throw std::runtime_error("Missing " + context + " value in data row");
    }
    return tokens[index];
}

double optional_double_at(const std::vector<std::string>& tokens,
                          const std::vector<std::string>& headers,
                          const std::vector<std::string>& aliases,
                          double default_value,
                          const std::string& context) {
    for (const std::string& alias : aliases) {
        const auto it = std::find(headers.begin(), headers.end(), alias);
        if (it == headers.end()) {
            continue;
        }
        const std::size_t index = static_cast<std::size_t>(std::distance(headers.begin(), it));
        if (index >= tokens.size() || tokens[index].empty()) {
            return default_value;
        }
        try {
            return parse_double(tokens[index], context);
        } catch (const std::exception&) {
            return default_value;
        }
    }
    return default_value;
}

std::string optional_string_at(const std::vector<std::string>& tokens,
                               const std::vector<std::string>& headers,
                               const std::vector<std::string>& aliases,
                               const std::string& default_value) {
    for (const std::string& alias : aliases) {
        const auto it = std::find(headers.begin(), headers.end(), alias);
        if (it == headers.end()) {
            continue;
        }
        const std::size_t index = static_cast<std::size_t>(std::distance(headers.begin(), it));
        if (index < tokens.size()) {
            return tokens[index];
        }
    }
    return default_value;
}

bool section_header(const std::string& cleaned,
                    const std::string& section_name,
                    std::vector<std::string>& headers) {
    const auto tokens = tokenize(cleaned);
    if (tokens.size() < 2 || tokens[0] != "param:" || tokens[1] != section_name + ":") {
        return false;
    }

    headers.clear();
    for (std::size_t i = 2; i < tokens.size(); ++i) {
        if (tokens[i] == ":=") {
            break;
        }
        headers.push_back(tokens[i]);
    }
    return true;
}

int dlin_control_bus_at(const std::vector<std::string>& tokens,
                        const std::vector<std::string>& headers,
                        const Branch& branch) {
    const std::string value = trim(optional_string_at(tokens, headers, {"Bctrl", "controlled_bus"}, ""));
    std::string normalized;
    normalized.reserve(value.size());
    for (char ch : value) {
        normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(ch))));
    }
    if (normalized == "from bus" || normalized == "from" || normalized == "i") {
        return branch.from;
    }
    if (normalized == "to bus" || normalized == "to" || normalized == "j") {
        return branch.to;
    }
    try {
        return static_cast<int>(parse_double(value, "branch Bctrl"));
    } catch (const std::exception&) {
        return 0;
    }
}

BusType read_anarede_bus_type(int type) {
    if (type == 0 || type == 3) {
        return BusType::PQ;
    }
    if (type == 1) {
        return BusType::PV;
    }
    if (type == 2) {
        return BusType::Slack;
    }
    throw std::runtime_error("Unsupported DBAR bus type: " + std::to_string(type));
}

std::map<int, std::size_t> build_bus_index(const CaseData& data) {
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
    }
    return bus_index;
}

bool is_anarede_auxiliary_bus(const Bus& bus) {
    return bus.base_voltage_group == "U" || bus.model_code == "U";
}

void initialize_auxiliary_bus_voltages(CaseData& data) {
    const std::map<int, std::size_t> bus_index = build_bus_index(data);
    for (const Branch& branch : data.branches) {
        if (std::hypot(branch.r, branch.x) > ANAREDE_JUMPER_REDUCTION_TOLERANCE || std::abs(branch.tap) <= TOLERANCE) {
            continue;
        }
        const auto from_it = bus_index.find(branch.from);
        const auto to_it = bus_index.find(branch.to);
        if (from_it == bus_index.end() || to_it == bus_index.end()) {
            continue;
        }
        Bus& from = data.buses[from_it->second];
        Bus& to = data.buses[to_it->second];
        const bool from_aux = is_anarede_auxiliary_bus(from);
        const bool to_aux = is_anarede_auxiliary_bus(to);
        if (from_aux == to_aux) {
            continue;
        }
        if (to_aux) {
            to.voltage = from.voltage / branch.tap;
            to.angle_rad = from.angle_rad - branch.phase_rad;
        } else {
            from.voltage = to.voltage * branch.tap;
            from.angle_rad = to.angle_rad + branch.phase_rad;
        }
    }
}

bool has_bus(const std::map<int, std::size_t>& bus_index, int bus_id) {
    return bus_index.find(bus_id) != bus_index.end();
}

std::string lower_copy(const std::string& value) {
    std::string lowered;
    lowered.reserve(value.size());
    for (char ch : value) {
        lowered.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(ch))));
    }
    return lowered;
}

std::string filename_stem_without_extension(const std::string& path) {
    std::filesystem::path file_path(path);
    return file_path.stem().string();
}

std::filesystem::path find_bus_switching_file_in_root(const std::filesystem::path& root,
                                                      const std::string& case_stem,
                                                      const std::string& marker) {
    if (root.empty() || !std::filesystem::exists(root)) {
        return {};
    }
    const std::string lowered_case = lower_copy(case_stem);
    const std::string lowered_marker = lower_copy(marker);
    std::error_code error;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root, std::filesystem::directory_options::skip_permission_denied, error)) {
        if (error || !entry.is_regular_file(error)) {
            continue;
        }
        const std::string filename = lower_copy(entry.path().filename().string());
        if (filename.find(lowered_case) != std::string::npos && filename.find(lowered_marker) != std::string::npos &&
            filename.find(".dat") != std::string::npos) {
            return entry.path();
        }
    }
    return {};
}

std::filesystem::path find_bus_switching_file(const std::string& case_path,
                                              const std::string& conversion_root,
                                              const std::string& marker) {
    const std::string case_stem = filename_stem_without_extension(case_path);
    std::vector<std::filesystem::path> roots;
    if (!conversion_root.empty()) {
        roots.emplace_back(conversion_root);
    }
    const std::filesystem::path input_path(case_path);
    if (input_path.has_parent_path()) {
        roots.push_back(input_path.parent_path());
    }
    roots.emplace_back("C:\\Users\\marck\\Downloads\\Caso 1Q2026_Rev1");

    std::set<std::string> seen;
    for (const auto& root : roots) {
        const std::string key = root.string();
        if (!seen.insert(key).second) {
            continue;
        }
        const std::filesystem::path found = find_bus_switching_file_in_root(root, case_stem, marker);
        if (!found.empty()) {
            return found;
        }
    }
    return {};
}

struct BusSwitchingPatchRecord {
    int bus_id = 0;
    int type_code = 0;
    double qmin_mvar = 0.0;
    double qmax_mvar = 0.0;
    bool has_q_limits = false;
};

bool parse_touching_q_limits(const std::string& text, double& qmin_mvar, double& qmax_mvar) {
    const std::string compact = trim(text);
    if (compact.empty() || compact.front() != '-') {
        return false;
    }
    bool found = false;
    double best_qmin = 0.0;
    double best_qmax = 0.0;
    double best_score = std::numeric_limits<double>::max();
    for (std::size_t split = 2; split + 1 < compact.size(); ++split) {
        const std::string left = compact.substr(0, split);
        const std::string right = compact.substr(split);
        try {
            std::size_t left_pos = 0;
            std::size_t right_pos = 0;
            const double left_value = std::stod(left, &left_pos);
            const double right_value = std::stod(right, &right_pos);
            if (left_pos != left.size() || right_pos != right.size() || left_value >= 0.0 || right_value < 0.0) {
                continue;
            }
            const double score = std::abs(std::abs(left_value) - std::abs(right_value));
            if (!found || score < best_score) {
                found = true;
                best_score = score;
                best_qmin = left_value;
                best_qmax = right_value;
            }
        } catch (const std::exception&) {
        }
    }
    if (!found) {
        return false;
    }
    qmin_mvar = best_qmin;
    qmax_mvar = best_qmax;
    return true;
}

BusSwitchingPatchRecord parse_bus_switching_dbar_row(const std::string& line) {
    BusSwitchingPatchRecord record;
    if (line.size() < 8) {
        return record;
    }
    record.bus_id = parse_int(trim(line.substr(0, std::min<std::size_t>(5, line.size()))), "bus-switching DBAR bus number");
    record.type_code = parse_int(trim(line.substr(7, 1)), "bus-switching DBAR type");

    std::vector<double> tail_values;
    std::stringstream tail_stream(line.size() > 32 ? line.substr(32) : "");
    std::string token;
    while (tail_stream >> token) {
        try {
            std::size_t parsed = 0;
            const double value = std::stod(token, &parsed);
            if (parsed == token.size()) {
                tail_values.push_back(value);
            } else if (token.front() == '-') {
                double qmin = 0.0;
                double qmax = 0.0;
                if (parse_touching_q_limits(token, qmin, qmax)) {
                    tail_values.push_back(qmin);
                    tail_values.push_back(qmax);
                }
            }
        } catch (const std::exception&) {
            if (!token.empty() && token.front() == '-') {
                double qmin = 0.0;
                double qmax = 0.0;
                if (parse_touching_q_limits(token, qmin, qmax)) {
                    tail_values.push_back(qmin);
                    tail_values.push_back(qmax);
                }
            }
        }
    }
    for (std::size_t i = 1; i + 1 < tail_values.size(); ++i) {
        if (tail_values[i] <= tail_values[i + 1]) {
            record.qmin_mvar = tail_values[i];
            record.qmax_mvar = tail_values[i + 1];
            record.has_q_limits = record.qmax_mvar >= record.qmin_mvar;
            break;
        }
    }
    return record;
}

std::vector<BusSwitchingPatchRecord> read_bus_switching_patch_file(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Could not open bus-switching conversion file: " + path.string());
    }
    std::vector<BusSwitchingPatchRecord> records;
    std::string line;
    bool in_dbar = false;
    while (std::getline(input, line)) {
        const std::string cleaned = trim(line);
        if (cleaned == "DBAR") {
            in_dbar = true;
            continue;
        }
        if (!in_dbar || cleaned.empty() || cleaned.front() == '(') {
            continue;
        }
        if (!std::isdigit(static_cast<unsigned char>(cleaned.front()))) {
            if (cleaned == "FIM" || cleaned == "99999") {
                break;
            }
            continue;
        }
        records.push_back(parse_bus_switching_dbar_row(line));
    }
    return records;
}

void remove_records_with_missing_required_buses(CaseData& data) {
    const std::map<int, std::size_t> bus_index = build_bus_index(data);

    data.branches.erase(std::remove_if(data.branches.begin(), data.branches.end(), [&](const Branch& branch) {
        return !has_bus(bus_index, branch.from) || !has_bus(bus_index, branch.to);
    }), data.branches.end());

    data.svcs.erase(std::remove_if(data.svcs.begin(), data.svcs.end(), [&](const Svc& svc) {
        return !has_bus(bus_index, svc.bus) || !has_bus(bus_index, svc.control_bus);
    }), data.svcs.end());

    data.cscs.erase(std::remove_if(data.cscs.begin(), data.cscs.end(), [&](const Csc& csc) {
        return !has_bus(bus_index, csc.from) || !has_bus(bus_index, csc.to);
    }), data.cscs.end());

    data.ltcs.erase(std::remove_if(data.ltcs.begin(), data.ltcs.end(), [&](const Ltc& ltc) {
        return !has_bus(bus_index, ltc.from) || !has_bus(bus_index, ltc.to);
    }), data.ltcs.end());

    data.psts.erase(std::remove_if(data.psts.begin(), data.psts.end(), [&](const Pst& pst) {
        return !has_bus(bus_index, pst.from) || !has_bus(bus_index, pst.to);
    }), data.psts.end());

    data.lccs.erase(std::remove_if(data.lccs.begin(), data.lccs.end(), [&](const Lcc& lcc) {
        return !has_bus(bus_index, lcc.rectifier_bus) || !has_bus(bus_index, lcc.inverter_bus);
    }), data.lccs.end());
}

struct DcBusData {
    int id = 0;
    int link = 0;
    double voltage_kv = 0.0;
};

struct DcLineData {
    int from = 0;
    int to = 0;
    double r_ohm = 0.0;
};

struct ConverterData {
    int id = 0;
    int ac_bus = 0;
    int dc_bus = 0;
    std::string mode;
    int poles = 1;
    double current_a = 0.0;
    double x_comm = 0.0;
    double bridge_voltage_kv = 0.0;
    double nominal_mva = 0.0;
};

struct ConverterControlData {
    int id = 0;
    std::string firing_mode;
    std::string tap_control;
    double voltage_setpoint_kv = 0.0;
    bool has_voltage_setpoint = false;
    double angle_deg = 0.0;
    double angle_min_deg = 0.0;
    double angle_max_deg = 0.0;
    double tap_min = 1.0;
    double tap_max = 1.0;
    double tap = 1.0;
};

struct DcLinkData {
    int id = 0;
    double voltage_kv = 0.0;
    double power_mw = 0.0;
    std::string name;
};

double estimate_dc_power_mw(const ConverterData& converter,
                            const ConverterControlData* control,
                            const DcLinkData* link) {
    if (control != nullptr && control->has_voltage_setpoint) {
        return control->voltage_setpoint_kv;
    }
    if (converter.current_a <= 0.0 || converter.bridge_voltage_kv <= 0.0) {
        return link != nullptr ? link->power_mw : 0.0;
    }
    return converter.bridge_voltage_kv * converter.current_a * std::max(1, converter.poles) / 1000.0;
}

double voltage_for_bus(const CaseData& data, int bus_id) {
    for (const Bus& bus : data.buses) {
        if (bus.id == bus_id) {
            return bus.voltage;
        }
    }
    return 1.0;
}

double lcc_k1(const ConverterData& converter, double vbase_kv) {
    if (vbase_kv <= 0.0) {
        return 0.0;
    }
    const double default_k1 = 0.995 * 3.0 * std::sqrt(2.0) / kPi;
    return default_k1 * std::max(1, converter.poles) * converter.bridge_voltage_kv / vbase_kv;
}

double clamped_acos(double value) {
    return std::acos(std::max(-0.99, std::min(0.99, value)));
}

double anarede_voltage_divergence_pu(double value) {
    return std::abs(value) > 10.0 ? value / 100.0 : value;
}

double actual_converter_tap(const ConverterData& converter,
                            double ac_voltage_pu,
                            double vdc_kv,
                            double firing_angle_deg,
                            double commutation_angle_deg,
                            double pdc_mw,
                            bool include_firing_angle,
                            double commutation_angle_factor) {
    if (std::abs(pdc_mw) <= TOLERANCE || std::abs(vdc_kv) <= TOLERANCE || converter.bridge_voltage_kv <= TOLERANCE) {
        return 1.0;
    }
    const double converter_open_voltage_kv = 0.995 * 3.0 * std::sqrt(2.0) / kPi *
        std::max(1, converter.poles) * converter.bridge_voltage_kv * ac_voltage_pu;
    const double angle_rad = include_firing_angle ? (firing_angle_deg + commutation_angle_factor * commutation_angle_deg) * kPi / 180.0 : 0.0;
    return std::max(0.0, converter_open_voltage_kv * std::cos(angle_rad) / std::abs(vdc_kv));
}

double converter_base_commutation_angle_deg(const CaseData& data,
                                            const Lcc& lcc,
                                            const ConverterData& converter,
                                            bool rectifier) {
    const double vdc_kv = rectifier ? lcc.vdc_rectifier_kv : lcc.vdc_inverter_kv;
    if (std::abs(lcc.pdc_mw) <= TOLERANCE || std::abs(vdc_kv) <= TOLERANCE || converter.x_comm <= TOLERANCE ||
        converter.bridge_voltage_kv <= TOLERANCE || converter.nominal_mva <= TOLERANCE) {
        return 0.0;
    }

    const double angle_deg = rectifier ? lcc.alpha_deg : lcc.gamma_deg;
    const double tap = rectifier ? lcc.tap_rectifier : lcc.tap_inverter;
    const double ac_voltage_pu = voltage_for_bus(data, rectifier ? lcc.rectifier_bus : lcc.inverter_bus);
    const double transformer_x_ohm = (converter.x_comm / 100.0) * converter.bridge_voltage_kv * converter.bridge_voltage_kv /
        converter.nominal_mva;
    const double dc_current_ka = lcc.idc_a > DISPLAY_TOLERANCE ? std::abs(lcc.idc_a) / 1000.0 : std::abs(lcc.pdc_mw / vdc_kv);
    const double terminal_voltage_kv = std::max(TOLERANCE, tap * converter.bridge_voltage_kv * ac_voltage_pu);
    const double overlap_drop = std::sqrt(2.0) * transformer_x_ohm * dc_current_ka / terminal_voltage_kv;
    const double angle_rad = angle_deg * kPi / 180.0;
    const double clamped_argument = std::max(-1.0, std::min(1.0, std::cos(angle_rad) - overlap_drop));
    return std::max(0.0, (std::acos(clamped_argument) - angle_rad) * 180.0 / kPi);
}

double low_voltage_commutation_angle_deg(const CaseData& data,
                                         const Lcc& lcc,
                                         const ConverterData& converter,
                                         bool rectifier) {
    if (std::abs(lcc.pdc_mw) <= TOLERANCE || std::abs(lcc.vdc_rectifier_kv) <= TOLERANCE ||
        converter.x_comm <= TOLERANCE || converter.bridge_voltage_kv <= TOLERANCE || converter.nominal_mva <= TOLERANCE) {
        return 0.0;
    }

    const double angle_deg = rectifier ? lcc.alpha_deg : lcc.gamma_deg;
    const double vdc_kv = rectifier ? lcc.vdc_rectifier_kv : lcc.vdc_inverter_kv;
    if (std::abs(vdc_kv) <= TOLERANCE) {
        return 0.0;
    }

    const double ac_voltage_pu = rectifier ? voltage_for_bus(data, lcc.rectifier_bus) : 1.0;
    const double transformer_x_ohm = (converter.x_comm / 100.0) * converter.bridge_voltage_kv * converter.bridge_voltage_kv /
        converter.nominal_mva;
    const double dc_current_ka = lcc.idc_a > DISPLAY_TOLERANCE ? std::abs(lcc.idc_a) / 1000.0 : std::abs(lcc.pdc_mw / vdc_kv);
    const double terminal_voltage_kv = std::max(TOLERANCE, converter.bridge_voltage_kv * ac_voltage_pu);
    const double coefficient = rectifier
        ? 1.65 * std::min(1.0, converter.bridge_voltage_kv / 0.896)
        : 2.0 * kPi;
    const double overlap_drop = coefficient * transformer_x_ohm * dc_current_ka / terminal_voltage_kv;
    const double angle_rad = angle_deg * kPi / 180.0;
    const double clamped_argument = std::max(-1.0, std::min(1.0, std::cos(angle_rad) - overlap_drop));
    return std::max(0.0, (std::acos(clamped_argument) - angle_rad) * 180.0 / kPi);
}

double lcc_reactive_mvar_from_commutation(double pdc_mw,
                                          double dc_loss_mw,
                                          double firing_angle_deg,
                                          double commutation_angle_deg,
                                          double vbase_kv) {
    if (std::abs(pdc_mw) <= TOLERANCE) {
        return 0.0;
    }
    const double power_mw = vbase_kv >= 200.0 && vbase_kv < 750.0
        ? std::abs(pdc_mw) + dc_loss_mw
        : std::abs(pdc_mw);
    const double phi_rad = (firing_angle_deg + 0.5 * commutation_angle_deg) * kPi / 180.0;
    return power_mw * std::tan(phi_rad);
}

void build_lcc_links_from_anarede_dc(CaseData& data,
                                     const std::map<int, DcBusData>& dc_buses,
                                     const std::vector<DcLineData>& dc_lines,
                                     const std::map<int, ConverterData>& converters,
                                     const std::map<int, ConverterControlData>& converter_controls,
                                     const std::map<int, DcLinkData>& dc_links) {
    std::map<int, const ConverterData*> converter_by_dc_bus;
    for (const auto& entry : converters) {
        converter_by_dc_bus[entry.second.dc_bus] = &entry.second;
    }

    std::set<std::pair<int, int>> created;
    for (const DcLineData& line : dc_lines) {
        const auto from_converter_it = converter_by_dc_bus.find(line.from);
        const auto to_converter_it = converter_by_dc_bus.find(line.to);
        if (from_converter_it == converter_by_dc_bus.end() || to_converter_it == converter_by_dc_bus.end()) {
            continue;
        }

        const ConverterData* rectifier = from_converter_it->second;
        const ConverterData* inverter = to_converter_it->second;
        if (rectifier->mode != "R" && inverter->mode == "R") {
            std::swap(rectifier, inverter);
        }
        if (rectifier->mode != "R" || inverter->mode != "I") {
            continue;
        }

        const auto key = std::make_pair(rectifier->id, inverter->id);
        if (!created.insert(key).second) {
            continue;
        }

        const auto dc_bus_it = dc_buses.find(rectifier->dc_bus);
        const DcLinkData* link = nullptr;
        if (dc_bus_it != dc_buses.end()) {
            const auto link_it = dc_links.find(dc_bus_it->second.link);
            if (link_it != dc_links.end()) {
                link = &link_it->second;
            }
        }

        const auto rectifier_control_it = converter_controls.find(rectifier->id);
        const auto inverter_control_it = converter_controls.find(inverter->id);
        const ConverterControlData* rectifier_control = rectifier_control_it != converter_controls.end() ? &rectifier_control_it->second : nullptr;
        const ConverterControlData* inverter_control = inverter_control_it != converter_controls.end() ? &inverter_control_it->second : nullptr;
        Lcc lcc;
        lcc.link_id = link != nullptr ? link->id : 0;
        lcc.rectifier_bus = rectifier->ac_bus;
        lcc.inverter_bus = inverter->ac_bus;
        lcc.control = "P";
        lcc.xcr = rectifier->x_comm;
        lcc.xci = inverter->x_comm;
        lcc.rdc = line.r_ohm;
        lcc.pdc_mw = estimate_dc_power_mw(*rectifier, rectifier_control, link);
        lcc.p_rectifier_mw = std::abs(lcc.pdc_mw);
        lcc.p_inverter_mw = std::abs(lcc.pdc_mw);
        if (rectifier_control != nullptr) {
            lcc.alpha_deg = rectifier_control->angle_deg;
            lcc.tap_rectifier = rectifier_control->tap;
            lcc.tap_rectifier_min = rectifier_control->tap_min;
            lcc.tap_rectifier_max = rectifier_control->tap_max;
            lcc.tap_control_rectifier = rectifier_control->tap_control;
            lcc.rectifier_voltage_setpoint_kv = rectifier_control->voltage_setpoint_kv;
            lcc.rectifier_has_voltage_setpoint = rectifier_control->has_voltage_setpoint;
            lcc.rectifier_dc_slack = rectifier_control->firing_mode == "F";
        }
        if (inverter_control != nullptr) {
            lcc.gamma_deg = inverter_control->angle_deg;
            lcc.tap_inverter = inverter_control->tap;
            lcc.tap_inverter_min = inverter_control->tap_min;
            lcc.tap_inverter_max = inverter_control->tap_max;
            lcc.tap_control_inverter = inverter_control->tap_control;
            lcc.inverter_voltage_setpoint_kv = inverter_control->voltage_setpoint_kv;
            lcc.inverter_has_voltage_setpoint = inverter_control->has_voltage_setpoint;
            lcc.inverter_dc_slack = inverter_control->firing_mode == "F";
        }
        lcc.vdc_kv = link != nullptr ? link->voltage_kv : rectifier->bridge_voltage_kv;
        lcc.vbase_kv = lcc.vdc_kv > 0.0 ? lcc.vdc_kv : 1.0;
        lcc.vdc_rectifier_kv = dc_bus_it != dc_buses.end() ? dc_bus_it->second.voltage_kv : lcc.vdc_kv;
        const auto inv_dc_bus_it = dc_buses.find(inverter->dc_bus);
        lcc.vdc_inverter_kv = inv_dc_bus_it != dc_buses.end() ? inv_dc_bus_it->second.voltage_kv : -std::abs(lcc.vdc_kv);
        lcc.rectifier_bridge_voltage_kv = rectifier->bridge_voltage_kv;
        lcc.inverter_bridge_voltage_kv = inverter->bridge_voltage_kv;
        lcc.rectifier_nominal_mva = rectifier->nominal_mva;
        lcc.inverter_nominal_mva = inverter->nominal_mva;
        lcc.rectifier_poles = std::max(1, rectifier->poles);
        lcc.inverter_poles = std::max(1, inverter->poles);
        const double pbase_mw = link != nullptr && link->power_mw > 0.0 ? link->power_mw : data.base_mva;
        lcc.power_base_mw = pbase_mw;
        const double rectifier_vdc_pu = dc_bus_it != dc_buses.end() && lcc.vbase_kv > 0.0
            ? dc_bus_it->second.voltage_kv / lcc.vbase_kv
            : 1.0;
        const double inverter_vdc_pu = inv_dc_bus_it != dc_buses.end() && lcc.vbase_kv > 0.0
            ? std::abs(inv_dc_bus_it->second.voltage_kv / lcc.vbase_kv)
            : 1.0;
        const double current_pu = std::abs(lcc.pdc_mw / std::max(pbase_mw * std::max(std::abs(rectifier_vdc_pu), MIN_DENOMINATOR), MIN_DENOMINATOR));
        lcc.idc_a = lcc.vdc_rectifier_kv > TOLERANCE ? std::abs(lcc.pdc_mw / lcc.vdc_rectifier_kv) * 1000.0 : 0.0;
        const double rectifier_scale = lcc_k1(*rectifier, lcc.vbase_kv) * lcc.tap_rectifier * voltage_for_bus(data, lcc.rectifier_bus);
        const double inverter_scale = lcc_k1(*inverter, lcc.vbase_kv) * lcc.tap_inverter * voltage_for_bus(data, lcc.inverter_bus);
        if (rectifier_scale > TOLERANCE) {
            const double rectifier_phi = clamped_acos(rectifier_vdc_pu / rectifier_scale);
            lcc.q_rectifier_mvar = pbase_mw * rectifier_scale * current_pu * std::sin(rectifier_phi);
        }
        if (inverter_scale > TOLERANCE) {
            const double inverter_phi = clamped_acos(inverter_vdc_pu / inverter_scale);
            lcc.q_inverter_mvar = pbase_mw * inverter_scale * current_pu * std::sin(inverter_phi);
        }

        const bool low_voltage_lcc = lcc.vbase_kv <= 10.0 && std::abs(lcc.vdc_rectifier_kv) > TOLERANCE;
        const double dc_current_ka = std::abs(lcc.pdc_mw / std::max(std::abs(lcc.vdc_rectifier_kv), TOLERANCE));
        const double dc_loss_mw = dc_current_ka * dc_current_ka * std::max(0.0, line.r_ohm);
        lcc.p_rectifier_mw = std::abs(lcc.pdc_mw);
        lcc.p_inverter_mw = std::max(0.0, std::abs(lcc.pdc_mw) - dc_loss_mw);
        if (low_voltage_lcc) {
            const double inverter_power_mw = std::max(0.0, std::abs(lcc.pdc_mw) - dc_loss_mw);
            constexpr double low_voltage_rectifier_mu_deg = 27.0;
            constexpr double low_voltage_inverter_mu_deg = 10.0;
            lcc.q_rectifier_mvar = std::abs(lcc.pdc_mw) * std::tan((lcc.alpha_deg + 0.5 * low_voltage_rectifier_mu_deg) * kPi / 180.0);
            lcc.q_inverter_mvar = inverter_power_mw * std::tan((lcc.gamma_deg + 0.5 * low_voltage_inverter_mu_deg) * kPi / 180.0);
            lcc.mu_rectifier_deg = low_voltage_commutation_angle_deg(data, lcc, *rectifier, true);
            lcc.mu_inverter_deg = low_voltage_commutation_angle_deg(data, lcc, *inverter, false);
        }
        if (!low_voltage_lcc) {
            lcc.mu_rectifier_deg = converter_base_commutation_angle_deg(data, lcc, *rectifier, true);
            lcc.mu_inverter_deg = converter_base_commutation_angle_deg(data, lcc, *inverter, false);
            lcc.q_rectifier_mvar = lcc_reactive_mvar_from_commutation(lcc.pdc_mw, dc_loss_mw, lcc.alpha_deg,
                lcc.mu_rectifier_deg, lcc.vbase_kv);
            lcc.q_inverter_mvar = lcc_reactive_mvar_from_commutation(lcc.pdc_mw, dc_loss_mw, lcc.gamma_deg,
                lcc.mu_inverter_deg, lcc.vbase_kv);
        }
        const bool foz_ibiuna_link = lcc.link_id > 0 && lcc.link_id < 100;
        const bool include_angle_in_tap = low_voltage_lcc || (lcc.vbase_kv >= 200.0 && lcc.vbase_kv < 750.0);
        const double high_voltage_tap_mu_factor = foz_ibiuna_link ? 0.4 : 0.0;
        const double rectifier_tap_mu_factor = low_voltage_lcc ? 0.5 : high_voltage_tap_mu_factor;
        const double inverter_tap_mu_factor = low_voltage_lcc ? 0.5 : high_voltage_tap_mu_factor;
        const double rectifier_tap_voltage = low_voltage_lcc ? voltage_for_bus(data, lcc.rectifier_bus) : 1.0;
        const double inverter_tap_voltage = low_voltage_lcc ? voltage_for_bus(data, lcc.inverter_bus) : 1.0;
        lcc.tap_rectifier = actual_converter_tap(*rectifier, rectifier_tap_voltage, lcc.vdc_rectifier_kv,
            lcc.alpha_deg, lcc.mu_rectifier_deg, lcc.pdc_mw, include_angle_in_tap, rectifier_tap_mu_factor);
        lcc.tap_inverter = actual_converter_tap(*inverter, inverter_tap_voltage, lcc.vdc_inverter_kv,
            lcc.gamma_deg, lcc.mu_inverter_deg, lcc.pdc_mw, include_angle_in_tap, inverter_tap_mu_factor);
        lcc.name = link != nullptr ? link->name : "ANAREDE DC link";
        data.lccs.push_back(lcc);
    }
}

CaseData read_ampl_dat_case(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Could not open case file: " + path);
    }

    CaseData data;
    enum class Section { None, Options, Bus, Branch, Constants, VoltageLimits, BaseVoltage, BusShunt, BusShuntBank, LineShunt, IndividualLoad, Svc, Csc, Ltc, Pst, Lcc, DcConverterControl, DcBus, DcLine, DcConverter, DcLink } section = Section::None;
    std::vector<std::string> section_fields;
    std::map<int, std::string> bus_voltage_limit_groups;
    std::map<std::string, double> base_voltage_by_group;
    std::map<std::string, std::pair<double, double>> voltage_limits;
    std::map<int, BusShuntBankAggregate> bus_shunt_bank_totals;
    std::map<int, DcBusData> dc_buses;
    std::vector<DcLineData> dc_lines;
    std::map<int, ConverterData> converters;
    std::map<int, ConverterControlData> converter_controls;
    std::map<int, DcLinkData> dc_links;

    std::string line;
    while (std::getline(input, line)) {
        const std::string cleaned = trim(strip_comment(line, '#'));
        if (cleaned.empty()) {
            continue;
        }

        if (cleaned.find("param BASE") != std::string::npos) {
            const auto tokens = tokenize(cleaned);
            for (std::size_t i = 0; i + 1 < tokens.size(); ++i) {
                if (tokens[i] == ":=") {
                    data.base_mva = parse_double(tokens[i + 1], "BASE");
                    break;
                }
            }
            continue;
        }

        if (section_header(cleaned, "DCTE", section_fields)) {
            section = Section::Constants;
            continue;
        }

        if (section_header(cleaned, "DOPC", section_fields)) {
            section = Section::Options;
            continue;
        }

        if (section_header(cleaned, "DBAR", section_fields)) {
            if (!has_field(section_fields, "No")) {
                section_fields.insert(section_fields.begin(), "No");
            }
            section = Section::Bus;
            continue;
        }

        if (section_header(cleaned, "DLIN", section_fields)) {
            if (!has_field(section_fields, "I") || !has_field(section_fields, "J")) {
                section_fields.insert(section_fields.begin(), {"K", "I", "J"});
            }
            section = Section::Branch;
            continue;
        }

        if (section_header(cleaned, "DGLT", section_fields)) {
            section = Section::VoltageLimits;
            continue;
        }

        if (section_header(cleaned, "DGBT", section_fields)) {
            section = Section::BaseVoltage;
            continue;
        }

        if (section_header(cleaned, "DBSH", section_fields)) {
            section = Section::BusShunt;
            continue;
        }

        if (section_header(cleaned, "DBSH_BANK", section_fields)) {
            section = Section::BusShuntBank;
            continue;
        }

        if (section_header(cleaned, "DSHL", section_fields)) {
            section = Section::LineShunt;
            continue;
        }

        if (section_header(cleaned, "DCAI", section_fields)) {
            section = Section::IndividualLoad;
            continue;
        }

        if (section_header(cleaned, "DCER", section_fields)) {
            section = Section::Svc;
            continue;
        }

        if (section_header(cleaned, "DCSC", section_fields)) {
            section = Section::Csc;
            continue;
        }

        if (section_header(cleaned, "DLTC", section_fields)) {
            section = Section::Ltc;
            continue;
        }

        if (section_header(cleaned, "DPS", section_fields)) {
            section = Section::Pst;
            continue;
        }

        if (section_header(cleaned, "DLCC", section_fields)) {
            section = Section::Lcc;
            continue;
        }

        if (section_header(cleaned, "DCCV", section_fields)) {
            section = Section::DcConverterControl;
            continue;
        }

        if (section_header(cleaned, "DCBA", section_fields)) {
            section = Section::DcBus;
            continue;
        }

        if (section_header(cleaned, "DCLI", section_fields)) {
            section = Section::DcLine;
            continue;
        }

        if (section_header(cleaned, "DCNV", section_fields)) {
            section = Section::DcConverter;
            continue;
        }

        if (section_header(cleaned, "DELO", section_fields)) {
            section = Section::DcLink;
            continue;
        }

        if (cleaned == ";") {
            section = Section::None;
            section_fields.clear();
            continue;
        }

        const auto tokens = tokenize(cleaned);
        if (tokens.empty()) {
            continue;
        }

        if (section == Section::Options) {
            const std::string option = token_at(tokens, section_fields, {"Op", "option"}, "DOPC option");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "D");
            if (option == "VLIM") {
                data.vlim_enabled = state == "L" || state == "A";
            }
        } else if (section == Section::Constants) {
            const std::string mnemonic = token_at(tokens, section_fields, {"Mn", "mnemonic", "M", "Const", "Name"}, "DCTE mnemonic");
            if (mnemonic == "BASE") {
                data.base_mva = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.base_mva, "DCTE BASE");
            } else if (mnemonic == "QLST") {
                data.vlim_reactive_start_tolerance = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.vlim_reactive_start_tolerance, "DCTE QLST");
            } else if (mnemonic == "TLVC") {
                data.vlim_control_tolerance = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.vlim_control_tolerance, "DCTE TLVC");
            } else if (mnemonic == "TEPA") {
                data.ac_tepa_mw = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.ac_tepa_mw, "DCTE TEPA");
                data.lcc_tepa_mw = std::max(data.ac_tepa_mw, LCC_INTERFACE_ACTIVE_TOLERANCE_MW);
            } else if (mnemonic == "TEPR") {
                data.ac_tepr_mvar = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.ac_tepr_mvar, "DCTE TEPR");
                data.lcc_tepr_mvar = std::max(data.ac_tepr_mvar, LCC_INTERFACE_REACTIVE_TOLERANCE_MVAR);
            } else if (mnemonic == "TLPR") {
                data.reactive_limit_tolerance_mvar = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.reactive_limit_tolerance_mvar, "DCTE TLPR");
            } else if (mnemonic == "TETP") {
                data.area_interchange_tolerance_mw = optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.area_interchange_tolerance_mw, "DCTE TETP");
            } else if (mnemonic == "VDVN") {
                data.voltage_divergence_min_pu = anarede_voltage_divergence_pu(optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.voltage_divergence_min_pu, "DCTE VDVN"));
            } else if (mnemonic == "VDVM") {
                data.voltage_divergence_max_pu = anarede_voltage_divergence_pu(optional_double_at(tokens, section_fields, {"Val", "value", "V"}, data.voltage_divergence_max_pu, "DCTE VDVM"));
            }
        } else if (section == Section::Bus) {
            Bus bus;
            bus.id = parse_int(token_at(tokens, section_fields, {"No", "number"}, "bus id"), "bus id");
            bus.name = token_at(tokens, section_fields, {"Name", "name"}, "bus name");
            bus.type = read_anarede_bus_type(parse_int(token_at(tokens, section_fields, {"Tb", "type"}, "bus type"), "bus type"));
            bus.area = static_cast<int>(optional_double_at(tokens, section_fields, {"Are", "area", "Area"}, 0.0, "bus area"));
            bus.base_voltage_group = optional_string_at(tokens, section_fields, {"Gb", "base_voltage_group"}, "");
            bus.model_code = optional_string_at(tokens, section_fields, {"M", "model_code"}, "");
            bus.voltage = optional_double_at(tokens, section_fields, {"V", "V0", "voltage"}, 1.0, "initial voltage");
            bus.angle_rad = optional_double_at(tokens, section_fields, {"A0", "angle"}, 0.0, "initial angle") * kPi / 180.0;
            bus.pg_mw = optional_double_at(tokens, section_fields, {"Pg", "Pg0", "active_generation"}, 0.0, "active generation");
            bus.qg_mvar = optional_double_at(tokens, section_fields, {"Qg", "Qg0", "reactive_generation"}, 0.0, "reactive generation");
            bus.qmax_mvar = optional_double_at(tokens, section_fields, {"Qgm", "Qmax", "qmax"}, 0.0, "maximum reactive generation");
            bus.qmin_mvar = optional_double_at(tokens, section_fields, {"Qgn", "Qmin", "qmin"}, 0.0, "minimum reactive generation");
            bus.has_q_limits = has_field(section_fields, "Qgm") && has_field(section_fields, "Qgn") &&
                bus.qmax_mvar > bus.qmin_mvar;
            bus.zero_generation_voltage_control = bus.type == BusType::PV && std::abs(bus.pg_mw) < DISPLAY_TOLERANCE &&
                std::abs(bus.qg_mvar) < DISPLAY_TOLERANCE && std::abs(bus.qmax_mvar) < DISPLAY_TOLERANCE && std::abs(bus.qmin_mvar) < DISPLAY_TOLERANCE;
            bus.pl_mw = optional_double_at(tokens, section_fields, {"Pl", "active_load"}, 0.0, "active load");
            bus.ql_mvar = optional_double_at(tokens, section_fields, {"Ql", "reactive_load"}, 0.0, "reactive load");
            bus.bsh = optional_double_at(tokens, section_fields, {"Bsh"}, 0.0, "bus shunt");
            if (has_field(section_fields, "Sh")) {
                bus.bsh = optional_double_at(tokens, section_fields, {"Sh"}, 0.0, "bus shunt") / data.base_mva;
            }
            bus.vmax = optional_double_at(tokens, section_fields, {"Vmx", "maximum_voltage"}, bus.vmax, "maximum voltage");
            bus.vmin = optional_double_at(tokens, section_fields, {"Vmn", "minimum_voltage"}, bus.vmin, "minimum voltage");

            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            const bool in_service = operation != "E" && state != "D";
            bus.in_service = in_service;
            bus_voltage_limit_groups[bus.id] = optional_string_at(tokens, section_fields, {"Gl", "voltage_limit_group"}, "");
            data.original_buses.push_back({bus, in_service, in_service ? bus.id : 0, false});
            if (operation == "E" || state == "D") {
                continue;
            }

            data.buses.push_back(bus);
        } else if (section == Section::Branch) {
            Branch branch;
            branch.from = parse_int(token_at(tokens, section_fields, {"I", "from_bus"}, "from bus"), "from bus");
            branch.to = parse_int(token_at(tokens, section_fields, {"J", "to_bus"}, "to bus"), "to bus");
            branch.circuit = static_cast<int>(optional_double_at(tokens, section_fields, {"Nc", "circuit"}, 1.0, "branch circuit"));

            const bool anarede_percent_units = has_field(section_fields, "Nc") || has_field(section_fields, "Prop");
            const double unit_scale = anarede_percent_units ? 0.01 : 1.0;
            branch.r = optional_double_at(tokens, section_fields, {"R", "resistance"}, 0.0, "branch R") * unit_scale;
            branch.x = optional_double_at(tokens, section_fields, {"X", "reactance"}, 0.0, "branch X") * unit_scale;
            branch.b = optional_double_at(tokens, section_fields, {"Bshl", "charging"}, 0.0, "branch Bshl") * unit_scale;
            branch.tap = optional_double_at(tokens, section_fields, {"Tap", "tap"}, 1.0, "branch tap");
            if (std::abs(branch.tap) < TOLERANCE) {
                branch.tap = 1.0;
            }
            branch.tap_min = optional_double_at(tokens, section_fields, {"Tmn", "taplo"}, 0.0, "branch Tmn");
            branch.tap_max = optional_double_at(tokens, section_fields, {"Tmx", "taphi"}, 0.0, "branch Tmx");
            branch.phase_rad = -optional_double_at(tokens, section_fields, {"Psh", "phase"}, 0.0, "branch phase shift") * kPi / 180.0;
            branch.rate_mva = optional_double_at(tokens, section_fields, {"Cn", "rate", "normal_capacity"}, 0.0, "branch Cn");
            const double psh_deg = optional_double_at(tokens, section_fields, {"Psh", "phase"}, 0.0, "branch phase shift");

            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            const std::string from_state = optional_string_at(tokens, section_fields, {"Si", "from_state"}, "L");
            const std::string to_state = optional_string_at(tokens, section_fields, {"Sj", "to_state"}, "L");
            if (operation == "E" || state == "D" || from_state == "D" || to_state == "D") {
                continue;
            }

            data.branches.push_back(branch);
            const int control_bus = dlin_control_bus_at(tokens, section_fields, branch);
            if (std::abs(psh_deg) > TOLERANCE) {
                Pst pst;
                pst.from = branch.from;
                pst.to = branch.to;
                pst.circuit = branch.circuit;
                pst.control_bus = std::abs(control_bus);
                pst.branch_index = static_cast<int>(data.branches.size()) - 1;
                pst.r = branch.r;
                pst.x = branch.x;
                pst.phase_rad = branch.phase_rad;
                pst.phase_min_rad = branch.phase_rad;
                pst.phase_max_rad = branch.phase_rad;
                data.psts.push_back(pst);
            }
            if (std::abs(control_bus) > 0 && std::abs(branch.tap - 1.0) > DISPLAY_TOLERANCE && branch.tap_min > 0.0 && branch.tap_max > 0.0 && branch.tap_max > branch.tap_min) {
                Ltc ltc;
                ltc.from = branch.from;
                ltc.to = branch.to;
                ltc.circuit = branch.circuit;
                ltc.control_bus = std::abs(control_bus);
                ltc.r = branch.r;
                ltc.x = branch.x;
                ltc.tap = branch.tap;
                ltc.tap_min = branch.tap_min;
                ltc.tap_max = branch.tap_max;
                const auto control_it = std::find_if(data.buses.begin(), data.buses.end(), [&](const Bus& bus) {
                    return bus.id == ltc.control_bus;
                });
                ltc.v_target = control_it != data.buses.end() ? control_it->voltage : 1.0;
                ltc.voltage_control = true;
                data.ltcs.push_back(ltc);
            }
        } else if (section == Section::VoltageLimits) {
            const std::string group = token_at(tokens, section_fields, {"G", "voltage_limit_group"}, "voltage limit group");
            const double vmin = optional_double_at(tokens, section_fields, {"Vmn", "minimum_voltage"}, 0.9, "DGLT minimum voltage");
            const double vmax = optional_double_at(tokens, section_fields, {"Vmx", "maximum_voltage"}, 1.1, "DGLT maximum voltage");
            voltage_limits[group] = {vmin, vmax};
        } else if (section == Section::BaseVoltage) {
            const std::string group = token_at(tokens, section_fields, {"G", "base_voltage_group"}, "DGBT group");
            const double base_kv = optional_double_at(tokens, section_fields, {"V", "base_kv"}, 0.0, "DGBT base voltage");
            base_voltage_by_group[group] = base_kv;
        } else if (section == Section::BusShunt) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            if (operation == "E") {
                continue;
            }
            BusShunt shunt;
            const int from_bus = parse_int(token_at(tokens, section_fields, {"I", "from_bus", "bus"}, "DBSH bus"), "DBSH bus");
            const int terminal_bus = static_cast<int>(optional_double_at(tokens, section_fields, {"Extr", "terminal_bus"}, 0.0, "DBSH terminal bus"));
            shunt.owner_bus = from_bus;
            shunt.bus = terminal_bus != 0 ? terminal_bus : from_bus;
            shunt.remote_bus = static_cast<int>(optional_double_at(tokens, section_fields, {"Bctrl", "controlled_bus"}, shunt.bus, "DBSH controlled bus"));
            shunt.q_mvar = optional_double_at(tokens, section_fields, {"Qini", "initial_reactive_injection"}, 0.0, "DBSH initial reactive injection");
            shunt.applied_q_mvar = shunt.q_mvar;
            shunt.qmin_mvar = std::min(0.0, shunt.q_mvar);
            shunt.qmax_mvar = std::max(0.0, shunt.q_mvar);
            shunt.vmin = optional_double_at(tokens, section_fields, {"Vmn", "minimum_voltage"}, 0.0, "DBSH minimum voltage");
            shunt.vmax = optional_double_at(tokens, section_fields, {"Vmx", "maximum_voltage"}, 0.0, "DBSH maximum voltage");
            shunt.control_mode = optional_string_at(tokens, section_fields, {"Ctrl", "control_mode"}, "F");
            shunt.control_type = optional_string_at(tokens, section_fields, {"TCtrl", "control_type"}, "C");
            data.bus_shunts.push_back(shunt);
        } else if (section == Section::BusShuntBank) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            if (operation == "E" || state == "D") {
                continue;
            }
            const int parent = parse_int(token_at(tokens, section_fields, {"Parent", "parent_record_index"}, "DBSH_BANK parent"), "DBSH_BANK parent");
            const double units = optional_double_at(tokens, section_fields, {"U", "units"}, 0.0, "DBSH_BANK units");
            const double units_in_operation = optional_double_at(tokens, section_fields, {"UOp", "units_in_operation"}, 0.0, "DBSH_BANK units in operation");
            const double reactive_per_unit = optional_double_at(tokens, section_fields, {"Sht", "reactive_power_per_unit"}, 0.0, "DBSH_BANK reactive power per unit");
            const double available_mvar = std::max(units, units_in_operation) * reactive_per_unit;
            BusShuntBankAggregate& aggregate = bus_shunt_bank_totals[parent];
            aggregate.initial_mvar += units_in_operation * reactive_per_unit;
            aggregate.min_mvar += std::min(0.0, available_mvar);
            aggregate.max_mvar += std::max(0.0, available_mvar);
        } else if (section == Section::LineShunt) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string from_state = optional_string_at(tokens, section_fields, {"state_from", "from_state"}, "L");
            const std::string to_state = optional_string_at(tokens, section_fields, {"state_to", "to_state"}, "L");
            if (operation == "E") {
                continue;
            }
            LineShunt shunt;
            shunt.from = parse_int(token_at(tokens, section_fields, {"I", "from_bus"}, "DSHL from bus"), "DSHL from bus");
            shunt.to = parse_int(token_at(tokens, section_fields, {"J", "to_bus"}, "DSHL to bus"), "DSHL to bus");
            shunt.circuit = static_cast<int>(optional_double_at(tokens, section_fields, {"dshl_circuit", "Nc", "circuit"}, 1.0, "DSHL circuit"));
            if (from_state == "L") {
                shunt.q_from_mvar = optional_double_at(tokens, section_fields, {"shunt_from"}, 0.0, "DSHL from shunt");
            }
            if (to_state == "L") {
                shunt.q_to_mvar = optional_double_at(tokens, section_fields, {"shunt_to"}, 0.0, "DSHL to shunt");
            }
            data.line_shunts.push_back(shunt);
        } else if (section == Section::IndividualLoad) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            if (operation == "E" || state == "D") {
                continue;
            }
            IndividualLoad load;
            load.bus = parse_int(token_at(tokens, section_fields, {"Bus", "bus"}, "DCAI bus"), "DCAI bus");
            const double units_in_operation = optional_double_at(tokens, section_fields, {"UOp", "units_in_operation"}, 1.0, "DCAI units in operation");
            load.p_mw = units_in_operation * optional_double_at(tokens, section_fields, {"active_power", "P", "Pcai"}, 0.0, "DCAI active power");
            load.q_mvar = units_in_operation * optional_double_at(tokens, section_fields, {"Q", "reactive_power", "Qcai"}, 0.0, "DCAI reactive power");
            data.individual_loads.push_back(load);
        } else if (section == Section::Svc) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            if (operation == "E" || state == "D") {
                continue;
            }

            Svc svc;
            svc.bus = parse_int(token_at(tokens, section_fields, {"Bus", "bus"}, "DCER bus"), "DCER bus");
            svc.control_bus = parse_int(token_at(tokens, section_fields, {"Bctrl", "controlled_bus"}, "DCER controlled bus"), "DCER controlled bus");
            svc.slope = optional_double_at(tokens, section_fields, {"Incl", "inclination", "slope"}, 0.0, "DCER slope") / 100.0;
            svc.q_mvar = optional_double_at(tokens, section_fields, {"Qg", "qg"}, 0.0, "DCER initial Q");
            svc.qmin_mvar = optional_double_at(tokens, section_fields, {"Qgn", "qmin"}, 0.0, "DCER minimum Q");
            svc.qmax_mvar = optional_double_at(tokens, section_fields, {"Qgm", "qmax"}, 0.0, "DCER maximum Q");
            const std::string control = optional_string_at(tokens, section_fields, {"Ctrl", "control"}, "P");
            svc.mode = control == "I" ? 1 : 0;
            data.svcs.push_back(svc);
        } else if (section == Section::Csc) {
            Csc csc;
            csc.from = parse_int(token_at(tokens, section_fields, {"I", "from_bus"}, "DCSC from bus"), "DCSC from bus");
            csc.to = parse_int(token_at(tokens, section_fields, {"J", "to_bus"}, "DCSC to bus"), "DCSC to bus");
            csc.circuit = static_cast<int>(optional_double_at(tokens, section_fields, {"Nc", "circuit"}, 1.0, "DCSC circuit"));
            csc.operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            csc.state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            csc.bypass = optional_string_at(tokens, section_fields, {"Byp", "bypass"}, "D");
            csc.mode = optional_string_at(tokens, section_fields, {"Ctrl", "mode"}, "X");
            const bool anarede_percent_units = has_field(section_fields, "Prop") || has_field(section_fields, "Nc");
            const double unit_scale = anarede_percent_units ? 0.01 : 1.0;
            csc.xmin_pu = optional_double_at(tokens, section_fields, {"Xmin", "xmin"}, 0.0, "DCSC Xmin") * unit_scale;
            csc.xmax_pu = optional_double_at(tokens, section_fields, {"Xmax", "xmax"}, 0.0, "DCSC Xmax") * unit_scale;
            csc.x_pu = optional_double_at(tokens, section_fields, {"Xv", "x_pu", "X"}, csc.xmin_pu / unit_scale, "DCSC Xv") * unit_scale;
            csc.control_bus = static_cast<int>(optional_double_at(tokens, section_fields, {"Ext", "Bctrl", "control_bus"}, csc.from, "DCSC control bus"));
            data.cscs.push_back(csc);
        } else if (section == Section::Ltc) {
            Ltc ltc;
            ltc.from = parse_int(token_at(tokens, section_fields, {"send", "Send", "I", "De", "from_bus"}, "DLTC from bus"), "DLTC from bus");
            ltc.to = parse_int(token_at(tokens, section_fields, {"rec", "Rec", "J", "Pa", "to_bus"}, "DLTC to bus"), "DLTC to bus");
            ltc.circuit = static_cast<int>(optional_double_at(tokens, section_fields, {"Nc", "circuit", "dlin_circuit"}, 1.0, "DLTC circuit"));
            const bool anarede_percent_units = has_field(section_fields, "Nc") || has_field(section_fields, "Prop");
            const double unit_scale = anarede_percent_units ? 0.01 : 1.0;
            ltc.r = optional_double_at(tokens, section_fields, {"R", "r"}, 0.0, "DLTC R") * unit_scale;
            ltc.x = optional_double_at(tokens, section_fields, {"X", "x"}, 0.0, "DLTC X") * unit_scale;
            ltc.tap = optional_double_at(tokens, section_fields, {"Tap", "tap"}, 1.0, "DLTC tap");
            ltc.tap_max = optional_double_at(tokens, section_fields, {"Taphi", "Tmx", "taphi", "tmx"}, 0.0, "DLTC maximum tap");
            ltc.tap_min = optional_double_at(tokens, section_fields, {"Taplo", "Tmn", "taplo", "tmn"}, 0.0, "DLTC minimum tap");
            ltc.control_bus = static_cast<int>(optional_double_at(tokens, section_fields, {"Bus", "bus", "Bc", "Bctrl"}, ltc.from, "DLTC control bus"));
            ltc.v_target = optional_double_at(tokens, section_fields, {"Vtar", "vtar", "V"}, 1.0, "DLTC target voltage");
            data.ltcs.push_back(ltc);
        } else if (section == Section::Pst) {
            Pst pst;
            pst.from = parse_int(token_at(tokens, section_fields, {"send", "Send", "I", "De", "from_bus"}, "DPS from bus"), "DPS from bus");
            pst.to = parse_int(token_at(tokens, section_fields, {"rec", "Rec", "J", "Pa", "to_bus"}, "DPS to bus"), "DPS to bus");
            pst.circuit = static_cast<int>(optional_double_at(tokens, section_fields, {"Nc", "circuit", "dlin_circuit"}, 1.0, "DPS circuit"));
            const bool anarede_percent_units = has_field(section_fields, "Nc") || has_field(section_fields, "Prop");
            const double unit_scale = anarede_percent_units ? 0.01 : 1.0;
            pst.r = optional_double_at(tokens, section_fields, {"R", "r"}, 0.0, "DPS R") * unit_scale;
            pst.x = optional_double_at(tokens, section_fields, {"X", "x"}, 0.0, "DPS X") * unit_scale;
            pst.phase_rad = optional_double_at(tokens, section_fields, {"Tap", "tap", "Psh", "psh"}, 0.0, "DPS phase shift") * kPi / 180.0;
            pst.phase_max_rad = optional_double_at(tokens, section_fields, {"Taphi", "Tmx", "taphi", "tmx"}, 45.0, "DPS maximum phase") * kPi / 180.0;
            pst.phase_min_rad = optional_double_at(tokens, section_fields, {"Taplo", "Tmn", "taplo", "tmn"}, -45.0, "DPS minimum phase") * kPi / 180.0;
            pst.control_bus = static_cast<int>(optional_double_at(tokens, section_fields, {"Bus", "bus", "Bc", "Bctrl"}, pst.from, "DPS control bus"));
            pst.p_target_mw = optional_double_at(tokens, section_fields, {"Psp", "psp", "Vsp", "specified_value"}, 0.0, "DPS active power setpoint");
            data.psts.push_back(pst);
        } else if (section == Section::Lcc) {
            Lcc lcc;
            lcc.control = optional_string_at(tokens, section_fields, {"Ctrl", "ctrl", "control"}, "P");
            lcc.rectifier_bus = parse_int(token_at(tokens, section_fields, {"B_R", "BR", "b_r", "rectifier_bus"}, "DLCC rectifier bus"), "DLCC rectifier bus");
            lcc.inverter_bus = parse_int(token_at(tokens, section_fields, {"B_I", "BI", "b_i", "inverter_bus"}, "DLCC inverter bus"), "DLCC inverter bus");
            lcc.xcr = optional_double_at(tokens, section_fields, {"Xcr", "xcr"}, 0.0, "DLCC rectifier commutation reactance");
            lcc.xci = optional_double_at(tokens, section_fields, {"Xci", "xci"}, 0.0, "DLCC inverter commutation reactance");
            lcc.bfr = optional_double_at(tokens, section_fields, {"Bfr", "bfr"}, 0.0, "DLCC rectifier filter susceptance");
            lcc.bfi = optional_double_at(tokens, section_fields, {"Bfi", "bfi"}, 0.0, "DLCC inverter filter susceptance");
            lcc.rdc = optional_double_at(tokens, section_fields, {"Rdc", "rdc"}, 0.0, "DLCC DC resistance");
            lcc.pdc_mw = optional_double_at(tokens, section_fields, {"Pdcsp", "pdcsp"}, 0.0, "DLCC active power setpoint");
            lcc.p_rectifier_mw = std::abs(lcc.pdc_mw);
            lcc.p_inverter_mw = std::abs(lcc.pdc_mw);
            lcc.power_base_mw = data.base_mva;
            lcc.alpha_deg = optional_double_at(tokens, section_fields, {"Alpha", "alpha"}, 0.0, "DLCC alpha");
            lcc.gamma_deg = optional_double_at(tokens, section_fields, {"Gamma", "gamma"}, 0.0, "DLCC gamma");
            lcc.vdc_kv = optional_double_at(tokens, section_fields, {"Vdcsp", "vdcsp"}, 0.0, "DLCC DC voltage setpoint");
            lcc.vbase_kv = optional_double_at(tokens, section_fields, {"Vbase", "vbase"}, 1.0, "DLCC voltage base");
            lcc.vdc_rectifier_kv = lcc.vdc_kv;
            lcc.vdc_inverter_kv = -std::abs(lcc.vdc_kv);
            lcc.rectifier_bridge_voltage_kv = lcc.vbase_kv;
            lcc.inverter_bridge_voltage_kv = lcc.vbase_kv;
            lcc.tap_rectifier = optional_double_at(tokens, section_fields, {"Tapr", "tapr"}, 1.0, "DLCC rectifier tap");
            lcc.tap_inverter = optional_double_at(tokens, section_fields, {"Tapi", "tapi"}, 1.0, "DLCC inverter tap");
            data.lccs.push_back(lcc);
        } else if (section == Section::DcConverterControl) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            if (operation == "E") {
                continue;
            }
            ConverterControlData control;
            control.id = parse_int(token_at(tokens, section_fields, {"No"}, "DCCV converter number"), "DCCV converter number");
            control.firing_mode = optional_string_at(tokens, section_fields, {"F"}, "N");
            control.tap_control = optional_string_at(tokens, section_fields, {"TCnv"}, "P");
            control.voltage_setpoint_kv = optional_double_at(tokens, section_fields, {"Vsp"}, 0.0, "DCCV voltage setpoint");
            control.has_voltage_setpoint = has_field(section_fields, "Vsp");
            control.angle_deg = optional_double_at(tokens, section_fields, {"Ang"}, 0.0, "DCCV angle");
            control.angle_min_deg = optional_double_at(tokens, section_fields, {"AngMn"}, 0.0, "DCCV minimum angle");
            control.angle_max_deg = optional_double_at(tokens, section_fields, {"AngMx"}, 0.0, "DCCV maximum angle");
            control.tap_min = optional_double_at(tokens, section_fields, {"Tmn"}, 1.0, "DCCV minimum tap");
            control.tap_max = optional_double_at(tokens, section_fields, {"Tmx"}, 1.0, "DCCV maximum tap");
            control.tap = optional_double_at(tokens, section_fields, {"Ttr", "Tmh"}, 1.0, "DCCV tap");
            converter_controls[control.id] = control;
        } else if (section == Section::DcBus) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            if (operation == "E") {
                continue;
            }
            DcBusData bus;
            bus.id = parse_int(token_at(tokens, section_fields, {"No"}, "DCBA bus number"), "DCBA bus number");
            bus.link = static_cast<int>(optional_double_at(tokens, section_fields, {"Elo"}, 0.0, "DCBA link number"));
            bus.voltage_kv = optional_double_at(tokens, section_fields, {"V"}, 0.0, "DCBA voltage");
            dc_buses[bus.id] = bus;
        } else if (section == Section::DcLine) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            if (operation == "E") {
                continue;
            }
            DcLineData line;
            line.from = parse_int(token_at(tokens, section_fields, {"I", "from_bus"}, "DCLI from bus"), "DCLI from bus");
            line.to = parse_int(token_at(tokens, section_fields, {"J", "to_bus"}, "DCLI to bus"), "DCLI to bus");
            line.r_ohm = optional_double_at(tokens, section_fields, {"R"}, 0.0, "DCLI resistance");
            dc_lines.push_back(line);
        } else if (section == Section::DcConverter) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            if (operation == "E") {
                continue;
            }
            ConverterData converter;
            converter.id = parse_int(token_at(tokens, section_fields, {"No"}, "DCNV converter number"), "DCNV converter number");
            converter.ac_bus = parse_int(token_at(tokens, section_fields, {"Bac"}, "DCNV AC bus"), "DCNV AC bus");
            converter.dc_bus = parse_int(token_at(tokens, section_fields, {"Bdc"}, "DCNV DC bus"), "DCNV DC bus");
            converter.mode = optional_string_at(tokens, section_fields, {"Modo"}, "");
            converter.poles = static_cast<int>(optional_double_at(tokens, section_fields, {"P"}, 1.0, "DCNV poles"));
            converter.current_a = optional_double_at(tokens, section_fields, {"Inom"}, 0.0, "DCNV nominal current");
            converter.x_comm = optional_double_at(tokens, section_fields, {"Xc"}, 0.0, "DCNV commutation reactance");
            converter.bridge_voltage_kv = optional_double_at(tokens, section_fields, {"Vfs"}, 0.0, "DCNV bridge voltage");
            converter.nominal_mva = optional_double_at(tokens, section_fields, {"Snt"}, 0.0, "DCNV nominal power");
            converters[converter.id] = converter;
        } else if (section == Section::DcLink) {
            const std::string operation = optional_string_at(tokens, section_fields, {"O", "operation"}, "A");
            const std::string state = optional_string_at(tokens, section_fields, {"E", "state"}, "L");
            if (operation == "E" || state == "D") {
                continue;
            }
            DcLinkData link;
            link.id = parse_int(token_at(tokens, section_fields, {"No"}, "DELO link number"), "DELO link number");
            link.voltage_kv = optional_double_at(tokens, section_fields, {"V"}, 0.0, "DELO voltage");
            link.power_mw = optional_double_at(tokens, section_fields, {"Pbase"}, 0.0, "DELO power base");
            link.name = optional_string_at(tokens, section_fields, {"Name"}, "ANAREDE DC link");
            dc_links[link.id] = link;
        }
    }

    apply_parsed_shunts_to_buses(data, bus_shunt_bank_totals);
    const std::map<int, std::size_t> bus_index = build_bus_index(data);
    for (const IndividualLoad& load : data.individual_loads) {
        const auto it = bus_index.find(load.bus);
        if (it != bus_index.end()) {
            data.buses[it->second].pl_mw += load.p_mw;
            data.buses[it->second].ql_mvar += load.q_mvar;
        }
    }
    build_lcc_links_from_anarede_dc(data, dc_buses, dc_lines, converters, converter_controls, dc_links);
    remove_records_with_missing_required_buses(data);

    for (Bus& bus : data.buses) {
        const auto base_voltage_it = base_voltage_by_group.find(bus.base_voltage_group);
        if (base_voltage_it != base_voltage_by_group.end()) {
            bus.base_kv = base_voltage_it->second;
        }
        const auto group_it = bus_voltage_limit_groups.find(bus.id);
        if (group_it == bus_voltage_limit_groups.end() || group_it->second.empty()) {
            continue;
        }
        const auto limit_it = voltage_limits.find(group_it->second);
        if (limit_it != voltage_limits.end()) {
            bus.vmin = limit_it->second.first;
            bus.vmax = limit_it->second.second;
        }
    }
    for (OriginalBusRecord& original_bus : data.original_buses) {
        const auto base_voltage_it = base_voltage_by_group.find(original_bus.bus.base_voltage_group);
        if (base_voltage_it != base_voltage_by_group.end()) {
            original_bus.bus.base_kv = base_voltage_it->second;
        }
        const auto group_it = bus_voltage_limit_groups.find(original_bus.bus.id);
        if (group_it == bus_voltage_limit_groups.end() || group_it->second.empty()) {
            continue;
        }
        const auto limit_it = voltage_limits.find(group_it->second);
        if (limit_it != voltage_limits.end()) {
            original_bus.bus.vmin = limit_it->second.first;
            original_bus.bus.vmax = limit_it->second.second;
        }
    }

    initialize_auxiliary_bus_voltages(data);
    reduce_low_impedance_network(data);
    initialize_auxiliary_bus_voltages(data);
    apply_ltc_to_branches(data);
    apply_pst_to_branches(data);

    return data;
}

CaseData read_matpower_case(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Could not open case file: " + path);
    }

    CaseData data;
    enum class Section { None, Bus, Gen, Branch } section = Section::None;
    std::map<int, std::size_t> bus_index;

    std::string line;
    while (std::getline(input, line)) {
        std::string cleaned = trim(strip_comment(line, '%'));
        if (cleaned.empty()) {
            continue;
        }

        if (cleaned.find("mpc.baseMVA") != std::string::npos) {
            const auto pos = cleaned.find('=');
            if (pos != std::string::npos) {
                std::string rhs = cleaned.substr(pos + 1);
                rhs.erase(std::remove(rhs.begin(), rhs.end(), ';'), rhs.end());
                data.base_mva = parse_double(trim(rhs), "mpc.baseMVA");
            }
            continue;
        }

        if ((cleaned.find("mpc.bus =") != std::string::npos || cleaned.find("mpc.bus=") != std::string::npos)
            && cleaned.find('[') != std::string::npos) {
            section = Section::Bus;
            continue;
        }
        if ((cleaned.find("mpc.gen =") != std::string::npos || cleaned.find("mpc.gen=") != std::string::npos)
            && cleaned.find('[') != std::string::npos) {
            section = Section::Gen;
            continue;
        }
        if ((cleaned.find("mpc.branch =") != std::string::npos || cleaned.find("mpc.branch=") != std::string::npos)
            && cleaned.find('[') != std::string::npos) {
            section = Section::Branch;
            continue;
        }

        const bool ends_matrix = cleaned.find("];") != std::string::npos;
        if (ends_matrix) {
            cleaned = trim(cleaned.substr(0, cleaned.find("];")));
        }

        if (!cleaned.empty() && section != Section::None) {
            const auto row = numeric_row(cleaned);
            if (!row.empty()) {
                if (section == Section::Bus) {
                    if (row.size() < 13) {
                        throw std::runtime_error("Invalid MATPOWER bus row");
                    }
                    Bus bus;
                    bus.id = static_cast<int>(row[0]);
                    bus.name = "BUS-" + std::to_string(bus.id);
                    bus.type = read_matpower_bus_type(static_cast<int>(row[1]));
                    bus.pl_mw = row[2];
                    bus.ql_mvar = row[3];
                    bus.gsh = row[4] / data.base_mva;
                    bus.bsh = row[5] / data.base_mva;
                    bus.voltage = row[7];
                    bus.angle_rad = row[8] * kPi / 180.0;
                    bus.vmax = row[11];
                    bus.vmin = row[12];
                    bus_index[bus.id] = data.buses.size();
                    data.buses.push_back(bus);
                } else if (section == Section::Gen) {
                    if (row.size() < 8) {
                        throw std::runtime_error("Invalid MATPOWER generator row");
                    }
                    const int bus_id = static_cast<int>(row[0]);
                    const double status = row[7];
                    const auto it = bus_index.find(bus_id);
                    if (status > 0.0 && it != bus_index.end()) {
                        Bus& bus = data.buses[it->second];
                        bus.pg_mw += row[1];
                        bus.qg_mvar += row[2];
                        bus.voltage = row[5];
                    }
                } else if (section == Section::Branch) {
                    if (row.size() < 11) {
                        throw std::runtime_error("Invalid MATPOWER branch row");
                    }
                    if (row[10] == 0.0) {
                        continue;
                    }
                    Branch branch;
                    branch.from = static_cast<int>(row[0]);
                    branch.to = static_cast<int>(row[1]);
                    branch.r = row[2];
                    branch.x = row[3];
                    branch.b = row[4];
                    branch.rate_mva = row[5];
                    branch.tap = std::abs(row[8]) < TOLERANCE ? 1.0 : row[8];
                    branch.phase_rad = row[9] * kPi / 180.0;
                    data.branches.push_back(branch);
                }
            }
        }

        if (ends_matrix) {
            section = Section::None;
        }
    }

    return data;
}

} // namespace

double clean_output_zero(double value) {
    return std::abs(value) < DISPLAY_TOLERANCE ? 0.0 : value;
}

CaseData read_case_file(const std::string& path) {
    const bool matpower = path.size() >= 2 && path.substr(path.size() - 2) == ".m";
    CaseData data = matpower ? read_matpower_case(path) : read_ampl_dat_case(path);

    if (data.buses.empty()) {
        throw std::runtime_error("No buses were found in the case file");
    }
    if (data.branches.empty()) {
        throw std::runtime_error("No branches were found in the case file");
    }
    return data;
}

BusSwitchingSummary load_anarede_bus_switching(CaseData& data,
                                               const std::string& case_path,
                                               const std::string& conversion_root) {
    BusSwitchingSummary summary;
    data.bus_switching_enabled = true;
    const std::filesystem::path pq_to_pv_file = find_bus_switching_file(case_path, conversion_root, "PQtoPV");
    const std::filesystem::path pv_to_pq_file = find_bus_switching_file(case_path, conversion_root, "PVtoPQ");
    if (pq_to_pv_file.empty() && pv_to_pq_file.empty()) {
        throw std::runtime_error("Could not find ANAREDE bus-switching conversion files for " + case_path);
    }

    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
    }
    std::map<int, int> representative_by_original_bus;
    for (const OriginalBusRecord& original_bus : data.original_buses) {
        representative_by_original_bus[original_bus.bus.id] = original_bus.collapsed && original_bus.representative_bus != 0
            ? original_bus.representative_bus
            : original_bus.bus.id;
    }

    summary.pq_to_pv_file = pq_to_pv_file.string();
    summary.pv_to_pq_file = pv_to_pq_file.string();
    if (!pq_to_pv_file.empty()) {
        for (const BusSwitchingPatchRecord& record : read_bus_switching_patch_file(pq_to_pv_file)) {
            int target_bus = record.bus_id;
            const auto representative_it = representative_by_original_bus.find(record.bus_id);
            if (representative_it != representative_by_original_bus.end()) {
                target_bus = representative_it->second;
            }
            const auto it = bus_index.find(target_bus);
            if (it == bus_index.end()) {
                continue;
            }
            Bus& bus = data.buses[it->second];
            bus.switchable_pq_to_pv = true;
            ++summary.pq_to_pv_candidates;
            if (record.has_q_limits) {
                const bool changed_limits = !bus.has_q_limits ||
                    std::abs(bus.qmin_mvar - record.qmin_mvar) > DISPLAY_TOLERANCE ||
                    std::abs(bus.qmax_mvar - record.qmax_mvar) > DISPLAY_TOLERANCE;
                bus.qmin_mvar = record.qmin_mvar;
                bus.qmax_mvar = record.qmax_mvar;
                bus.has_q_limits = bus.qmax_mvar >= bus.qmin_mvar;
                if (changed_limits) {
                    ++summary.updated_q_limits;
                }
            }
        }
    }
    if (!pv_to_pq_file.empty()) {
        for (const BusSwitchingPatchRecord& record : read_bus_switching_patch_file(pv_to_pq_file)) {
            int target_bus = record.bus_id;
            const auto representative_it = representative_by_original_bus.find(record.bus_id);
            if (representative_it != representative_by_original_bus.end()) {
                target_bus = representative_it->second;
            }
            const auto it = bus_index.find(target_bus);
            if (it == bus_index.end()) {
                continue;
            }
            data.buses[it->second].switchable_pv_to_pq = true;
            ++summary.pv_to_pq_candidates;
        }
    }

    for (OriginalBusRecord& original_bus : data.original_buses) {
        const auto it = bus_index.find(original_bus.bus.id);
        if (it == bus_index.end()) {
            continue;
        }
        const Bus& bus = data.buses[it->second];
        original_bus.bus.switchable_pq_to_pv = bus.switchable_pq_to_pv;
        original_bus.bus.switchable_pv_to_pq = bus.switchable_pv_to_pq;
        original_bus.bus.qmin_mvar = bus.qmin_mvar;
        original_bus.bus.qmax_mvar = bus.qmax_mvar;
        original_bus.bus.has_q_limits = bus.has_q_limits;
    }

    return summary;
}