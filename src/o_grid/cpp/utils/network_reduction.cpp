#include "../headers/utils/network_reduction.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <map>
#include <limits>
#include <set>
#include <stdexcept>
#include <vector>

namespace {

class DisjointSet {
public:
    explicit DisjointSet(std::size_t size) : parent_(size), rank_(size, 0) {
        for (std::size_t i = 0; i < size; ++i) {
            parent_[i] = static_cast<int>(i);
        }
    }

    int find(int value) {
        if (parent_[value] != value) {
            parent_[value] = find(parent_[value]);
        }
        return parent_[value];
    }

    void unite(int first, int second) {
        int first_root = find(first);
        int second_root = find(second);
        if (first_root == second_root) {
            return;
        }
        if (rank_[first_root] < rank_[second_root]) {
            std::swap(first_root, second_root);
        }
        parent_[second_root] = first_root;
        if (rank_[first_root] == rank_[second_root]) {
            ++rank_[first_root];
        }
    }

private:
    std::vector<int> parent_;
    std::vector<int> rank_;
};

int remap_required_bus(const std::map<int, int>& representative_by_bus, int bus_id, const std::string& context) {
    const auto it = representative_by_bus.find(bus_id);
    if (it == representative_by_bus.end()) {
        throw std::runtime_error(context + " references an unknown bus: " + std::to_string(bus_id));
    }
    return it->second;
}

int remap_optional_bus(const std::map<int, int>& representative_by_bus, int bus_id) {
    const auto it = representative_by_bus.find(bus_id);
    return it == representative_by_bus.end() ? bus_id : it->second;
}

bool same_voltage_level(const Bus& first, const Bus& second) {
    if (!first.base_voltage_group.empty() && first.base_voltage_group == second.base_voltage_group) {
        return true;
    }
    return first.base_kv > 0.0 && second.base_kv > 0.0 && std::abs(first.base_kv - second.base_kv) <= DISPLAY_TOLERANCE;
}

double initial_apparent_flow_mva(const Branch& branch, const Bus& from, const Bus& to, double base_mva) {
    const std::complex<double> z(branch.r, branch.x);
    if (std::abs(z) <= TOLERANCE) {
        return std::numeric_limits<double>::infinity();
    }
    const std::complex<double> y = 1.0 / z;
    const std::complex<double> charging(0.0, branch.b / 2.0);
    const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);
    const std::complex<double> vf = std::polar(from.voltage, from.angle_rad);
    const std::complex<double> vt = std::polar(to.voltage, to.angle_rad);
    const std::complex<double> current = ((y + charging) / (tap * std::conj(tap))) * vf - (y / std::conj(tap)) * vt;
    return std::abs(vf * std::conj(current)) * base_mva;
}

bool has_suspicious_initial_jumper_flow(const Branch& branch, const Bus& from, const Bus& to, double base_mva) {
    if (branch.rate_mva <= 0.0 || std::abs(branch.tap - 1.0) > DISPLAY_TOLERANCE || std::abs(branch.phase_rad) > DISPLAY_TOLERANCE) {
        return false;
    }
    if (!same_voltage_level(from, to) || std::hypot(branch.r, branch.x) > ANAREDE_JUMPER_REDUCTION_TOLERANCE) {
        return false;
    }

    const double apparent_mva = initial_apparent_flow_mva(branch, from, to, base_mva);
    return apparent_mva > branch.rate_mva * ANAREDE_JUMPER_FLOW_MARGIN;
}

bool should_reduce_branch(const CaseData& data, const std::map<int, int>& bus_position, const Branch& branch) {
    if (std::hypot(branch.r, branch.x) <= LOW_IMPEDANCE_REDUCTION_TOLERANCE) {
        return true;
    }
    const auto from_it = bus_position.find(branch.from);
    const auto to_it = bus_position.find(branch.to);
    if (from_it == bus_position.end() || to_it == bus_position.end()) {
        return false;
    }
    const Bus& from = data.buses[static_cast<std::size_t>(from_it->second)];
    const Bus& to = data.buses[static_cast<std::size_t>(to_it->second)];
    return has_suspicious_initial_jumper_flow(
        branch,
        from,
        to,
        data.base_mva);
}

bool selected_by_options(const Bus& bus,
                         const std::set<int>& buses,
                         const std::set<int>& areas,
                         const std::set<std::string>& voltage_groups) {
    return buses.find(bus.id) != buses.end() ||
        areas.find(bus.area) != areas.end() ||
        voltage_groups.find(bus.base_voltage_group) != voltage_groups.end();
}

std::vector<std::vector<std::complex<double>>> make_matrix(int rows, int cols) {
    return std::vector<std::vector<std::complex<double>>>(
        static_cast<std::size_t>(rows),
        std::vector<std::complex<double>>(static_cast<std::size_t>(cols), std::complex<double>(0.0, 0.0)));
}

std::vector<std::vector<std::complex<double>>> solve_complex_linear_system(
    std::vector<std::vector<std::complex<double>>> matrix,
    std::vector<std::vector<std::complex<double>>> rhs) {
    const int n = static_cast<int>(matrix.size());
    const int cols = rhs.empty() ? 0 : static_cast<int>(rhs.front().size());
    for (int pivot = 0; pivot < n; ++pivot) {
        int best = pivot;
        double best_abs = std::abs(matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(pivot)]);
        for (int row = pivot + 1; row < n; ++row) {
            const double value = std::abs(matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(pivot)]);
            if (value > best_abs) {
                best = row;
                best_abs = value;
            }
        }
        if (best_abs <= TOLERANCE) {
            throw std::runtime_error("Ward reduction external admittance matrix is singular");
        }
        if (best != pivot) {
            std::swap(matrix[static_cast<std::size_t>(best)], matrix[static_cast<std::size_t>(pivot)]);
            std::swap(rhs[static_cast<std::size_t>(best)], rhs[static_cast<std::size_t>(pivot)]);
        }
        const std::complex<double> diag = matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(pivot)];
        for (int col = pivot; col < n; ++col) {
            matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)] /= diag;
        }
        for (int col = 0; col < cols; ++col) {
            rhs[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)] /= diag;
        }
        for (int row = 0; row < n; ++row) {
            if (row == pivot) {
                continue;
            }
            const std::complex<double> factor = matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(pivot)];
            if (std::abs(factor) <= TOLERANCE) {
                continue;
            }
            for (int col = pivot; col < n; ++col) {
                matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)] -= factor * matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)];
            }
            for (int col = 0; col < cols; ++col) {
                rhs[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)] -= factor * rhs[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)];
            }
        }
    }
    return rhs;
}

void add_series_only_branch_to_matrix(const Branch& branch,
                                      int from,
                                      int to,
                                      std::vector<std::vector<std::complex<double>>>& ybus) {
    const std::complex<double> z(branch.r, branch.x);
    if (std::abs(z) <= TOLERANCE) {
        return;
    }
    const std::complex<double> y = 1.0 / z;
    const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);
    ybus[static_cast<std::size_t>(from)][static_cast<std::size_t>(from)] += y / (tap * std::conj(tap));
    ybus[static_cast<std::size_t>(to)][static_cast<std::size_t>(to)] += y;
    ybus[static_cast<std::size_t>(from)][static_cast<std::size_t>(to)] -= y / std::conj(tap);
    ybus[static_cast<std::size_t>(to)][static_cast<std::size_t>(from)] -= y / tap;
}

std::complex<double> branch_power_from_end(const Branch& branch, const Bus& from_bus, const Bus& to_bus, double base_mva) {
    const std::complex<double> z(branch.r, branch.x);
    if (std::abs(z) <= TOLERANCE) {
        return std::complex<double>(0.0, 0.0);
    }
    const std::complex<double> y = 1.0 / z;
    const std::complex<double> charging(0.0, branch.b / 2.0);
    const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);
    const std::complex<double> vf = std::polar(from_bus.voltage, from_bus.angle_rad);
    const std::complex<double> vt = std::polar(to_bus.voltage, to_bus.angle_rad);
    const std::complex<double> current = ((y + charging) / (tap * std::conj(tap))) * vf - (y / std::conj(tap)) * vt;
    return vf * std::conj(current) * base_mva;
}

void remove_missing_device_records(CaseData& data) {
    std::set<int> buses;
    for (const Bus& bus : data.buses) {
        buses.insert(bus.id);
    }
    const auto has_bus = [&](int bus_id) {
        return bus_id == 0 || buses.find(bus_id) != buses.end();
    };
    data.bus_shunts.erase(std::remove_if(data.bus_shunts.begin(), data.bus_shunts.end(), [&](const BusShunt& shunt) {
        return !has_bus(shunt.bus) || !has_bus(shunt.owner_bus) || !has_bus(shunt.remote_bus);
    }), data.bus_shunts.end());
    data.line_shunts.erase(std::remove_if(data.line_shunts.begin(), data.line_shunts.end(), [&](const LineShunt& shunt) {
        return !has_bus(shunt.from) || !has_bus(shunt.to);
    }), data.line_shunts.end());
    data.svcs.erase(std::remove_if(data.svcs.begin(), data.svcs.end(), [&](const Svc& svc) {
        return !has_bus(svc.bus) || !has_bus(svc.control_bus);
    }), data.svcs.end());
    data.cscs.erase(std::remove_if(data.cscs.begin(), data.cscs.end(), [&](const Csc& csc) {
        return !has_bus(csc.from) || !has_bus(csc.to) || !has_bus(csc.control_bus);
    }), data.cscs.end());
    data.ltcs.erase(std::remove_if(data.ltcs.begin(), data.ltcs.end(), [&](const Ltc& ltc) {
        return !has_bus(ltc.from) || !has_bus(ltc.to) || !has_bus(ltc.control_bus);
    }), data.ltcs.end());
    data.psts.erase(std::remove_if(data.psts.begin(), data.psts.end(), [&](const Pst& pst) {
        return !has_bus(pst.from) || !has_bus(pst.to) || !has_bus(pst.control_bus);
    }), data.psts.end());
    data.lccs.erase(std::remove_if(data.lccs.begin(), data.lccs.end(), [&](const Lcc& lcc) {
        return !has_bus(lcc.rectifier_bus) || !has_bus(lcc.inverter_bus);
    }), data.lccs.end());
}

} // namespace

void reduce_low_impedance_network(CaseData& data) {
    if (data.buses.empty()) {
        return;
    }

    std::map<int, int> bus_position;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_position[data.buses[i].id] = static_cast<int>(i);
    }

    DisjointSet groups(data.buses.size());
    for (const Branch& branch : data.branches) {
        if (!should_reduce_branch(data, bus_position, branch)) {
            continue;
        }
        const auto from_it = bus_position.find(branch.from);
        const auto to_it = bus_position.find(branch.to);
        if (from_it != bus_position.end() && to_it != bus_position.end()) {
            groups.unite(from_it->second, to_it->second);
        }
    }

    std::map<int, std::vector<int>> members_by_root;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        members_by_root[groups.find(static_cast<int>(i))].push_back(static_cast<int>(i));
    }

    std::vector<int> external_degree(data.buses.size(), 0);
    for (const Branch& branch : data.branches) {
        const auto from_it = bus_position.find(branch.from);
        const auto to_it = bus_position.find(branch.to);
        if (from_it == bus_position.end() || to_it == bus_position.end()) {
            continue;
        }
        if (groups.find(from_it->second) != groups.find(to_it->second)) {
            ++external_degree[static_cast<std::size_t>(from_it->second)];
            ++external_degree[static_cast<std::size_t>(to_it->second)];
        }
    }

    std::map<int, int> representative_by_bus;
    for (const auto& entry : members_by_root) {
        const std::vector<int>& members = entry.second;
        int representative = members.front();
        for (int member : members) {
            if (data.buses[member].type == BusType::Slack) {
                representative = member;
                break;
            }
            if (data.buses[member].type == BusType::PV && data.buses[representative].type == BusType::PQ) {
                representative = member;
                continue;
            }
            if (data.buses[member].type == data.buses[representative].type &&
                external_degree[static_cast<std::size_t>(member)] > external_degree[static_cast<std::size_t>(representative)]) {
                representative = member;
            }
        }
        for (int member : members) {
            representative_by_bus[data.buses[member].id] = data.buses[representative].id;
        }
    }

    for (OriginalBusRecord& original_bus : data.original_buses) {
        if (!original_bus.in_service) {
            original_bus.representative_bus = 0;
            original_bus.collapsed = false;
            continue;
        }
        const auto representative_it = representative_by_bus.find(original_bus.bus.id);
        original_bus.representative_bus = representative_it != representative_by_bus.end()
            ? representative_it->second
            : original_bus.bus.id;
        original_bus.collapsed = original_bus.representative_bus != original_bus.bus.id;
    }

    for (Bus& bus : data.buses) {
        const int representative_id = representative_by_bus[bus.id];
        if (representative_id == bus.id) {
            continue;
        }
        Bus& representative = data.buses[static_cast<std::size_t>(bus_position[representative_id])];
        representative.pg_mw += bus.pg_mw;
        representative.qg_mvar += bus.qg_mvar;
        representative.pl_mw += bus.pl_mw;
        representative.ql_mvar += bus.ql_mvar;
        representative.gsh += bus.gsh;
        representative.bsh += bus.bsh;
    }

    std::vector<Bus> collapsed_buses;
    collapsed_buses.reserve(data.buses.size());
    for (const Bus& bus : data.buses) {
        if (representative_by_bus[bus.id] == bus.id) {
            collapsed_buses.push_back(bus);
        }
    }
    data.buses = collapsed_buses;

    for (Branch& branch : data.branches) {
        branch.from = remap_required_bus(representative_by_bus, branch.from, "Branch");
        branch.to = remap_required_bus(representative_by_bus, branch.to, "Branch");
    }
    data.branches.erase(std::remove_if(data.branches.begin(), data.branches.end(), [](const Branch& branch) {
        return branch.from == branch.to;
    }), data.branches.end());

    for (Svc& svc : data.svcs) {
        svc.bus = remap_required_bus(representative_by_bus, svc.bus, "DCER");
        svc.control_bus = remap_required_bus(representative_by_bus, svc.control_bus, "DCER");
    }
    for (BusShunt& shunt : data.bus_shunts) {
        shunt.owner_bus = remap_optional_bus(representative_by_bus, shunt.owner_bus);
        shunt.bus = remap_optional_bus(representative_by_bus, shunt.bus);
        shunt.remote_bus = remap_optional_bus(representative_by_bus, shunt.remote_bus);
    }
    data.bus_shunts.erase(std::remove_if(data.bus_shunts.begin(), data.bus_shunts.end(), [](const BusShunt& shunt) {
        return shunt.bus == 0;
    }), data.bus_shunts.end());
    for (LineShunt& shunt : data.line_shunts) {
        shunt.from = remap_optional_bus(representative_by_bus, shunt.from);
        shunt.to = remap_optional_bus(representative_by_bus, shunt.to);
    }
    data.line_shunts.erase(std::remove_if(data.line_shunts.begin(), data.line_shunts.end(), [](const LineShunt& shunt) {
        return shunt.from == 0 || shunt.to == 0 || shunt.from == shunt.to;
    }), data.line_shunts.end());
    for (Csc& csc : data.cscs) {
        csc.from = remap_required_bus(representative_by_bus, csc.from, "DCSC");
        csc.to = remap_required_bus(representative_by_bus, csc.to, "DCSC");
        csc.control_bus = remap_optional_bus(representative_by_bus, csc.control_bus);
    }
    for (Ltc& ltc : data.ltcs) {
        ltc.from = remap_required_bus(representative_by_bus, ltc.from, "DLTC");
        ltc.to = remap_required_bus(representative_by_bus, ltc.to, "DLTC");
        ltc.control_bus = remap_optional_bus(representative_by_bus, ltc.control_bus);
    }
    for (Pst& pst : data.psts) {
        pst.from = remap_required_bus(representative_by_bus, pst.from, "DPS");
        pst.to = remap_required_bus(representative_by_bus, pst.to, "DPS");
        pst.control_bus = remap_optional_bus(representative_by_bus, pst.control_bus);
    }
    for (Lcc& lcc : data.lccs) {
        lcc.rectifier_bus = remap_required_bus(representative_by_bus, lcc.rectifier_bus, "LCC-HVDC");
        lcc.inverter_bus = remap_required_bus(representative_by_bus, lcc.inverter_bus, "LCC-HVDC");
    }
}

EquivalentReductionSummary apply_equivalent_network_reduction(CaseData& data, const EquivalentReductionOptions& options) {
    EquivalentReductionSummary summary;
    summary.method = options.method;
    if (options.method == EquivalentReductionMethod::None || data.buses.empty()) {
        return summary;
    }

    const bool has_explicit_selection = !options.retained_buses.empty() || !options.external_buses.empty() ||
        !options.retained_areas.empty() || !options.external_areas.empty() ||
        !options.retained_voltage_groups.empty() || !options.external_voltage_groups.empty();
    std::set<int> default_retained_buses;
    if (!has_explicit_selection && options.method == EquivalentReductionMethod::Ward) {
        std::map<int, int> branch_degree;
        for (const Branch& branch : data.branches) {
            ++branch_degree[branch.from];
            ++branch_degree[branch.to];
        }
        for (const Bus& bus : data.buses) {
            const bool has_power_injection = std::abs(bus.pg_mw) > DISPLAY_TOLERANCE ||
                std::abs(bus.qg_mvar) > DISPLAY_TOLERANCE || std::abs(bus.pl_mw) > DISPLAY_TOLERANCE ||
                std::abs(bus.ql_mvar) > DISPLAY_TOLERANCE || std::abs(bus.gsh) > DISPLAY_TOLERANCE ||
                std::abs(bus.bsh) > DISPLAY_TOLERANCE;
            const auto degree_it = branch_degree.find(bus.id);
            const int degree = degree_it != branch_degree.end() ? degree_it->second : 0;
            if (degree != 1 || bus.type != BusType::PQ || has_power_injection || bus.has_q_limits || bus.zero_generation_voltage_control) {
                default_retained_buses.insert(bus.id);
            }
        }
        for (const BusShunt& shunt : data.bus_shunts) {
            default_retained_buses.insert(shunt.bus);
            default_retained_buses.insert(shunt.owner_bus);
            default_retained_buses.insert(shunt.remote_bus);
        }
        for (const LineShunt& shunt : data.line_shunts) {
            default_retained_buses.insert(shunt.from);
            default_retained_buses.insert(shunt.to);
        }
        for (const Svc& svc : data.svcs) {
            default_retained_buses.insert(svc.bus);
            default_retained_buses.insert(svc.control_bus);
        }
        for (const Csc& csc : data.cscs) {
            default_retained_buses.insert(csc.from);
            default_retained_buses.insert(csc.to);
            default_retained_buses.insert(csc.control_bus);
        }
        for (const Ltc& ltc : data.ltcs) {
            default_retained_buses.insert(ltc.from);
            default_retained_buses.insert(ltc.to);
            default_retained_buses.insert(ltc.control_bus);
        }
        for (const Pst& pst : data.psts) {
            default_retained_buses.insert(pst.from);
            default_retained_buses.insert(pst.to);
            default_retained_buses.insert(pst.control_bus);
        }
        for (const Lcc& lcc : data.lccs) {
            default_retained_buses.insert(lcc.rectifier_bus);
            default_retained_buses.insert(lcc.inverter_bus);
        }
    }
    const bool use_default_ward_selection = !default_retained_buses.empty();
    if (!has_explicit_selection && !use_default_ward_selection) {
        summary.retained_buses = static_cast<int>(data.buses.size());
        return summary;
    }

    std::map<int, int> bus_position;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_position[data.buses[i].id] = static_cast<int>(i);
    }

    std::set<int> external_ids;
    std::set<int> retained_ids;
    for (const Bus& bus : data.buses) {
        const bool selected_external = selected_by_options(
            bus,
            options.external_buses,
            options.external_areas,
            options.external_voltage_groups) ||
            (use_default_ward_selection && default_retained_buses.find(bus.id) == default_retained_buses.end());
        const bool selected_retained = selected_by_options(
            bus,
            options.retained_buses,
            options.retained_areas,
            options.retained_voltage_groups) ||
            (use_default_ward_selection && default_retained_buses.find(bus.id) != default_retained_buses.end());
        if (selected_external && !selected_retained) {
            external_ids.insert(bus.id);
        } else if (selected_retained || use_default_ward_selection ||
            (!options.retained_buses.empty() || !options.retained_areas.empty() || !options.retained_voltage_groups.empty())) {
            retained_ids.insert(bus.id);
        }
    }
    if (external_ids.empty() && (!options.retained_buses.empty() || !options.retained_areas.empty() || !options.retained_voltage_groups.empty())) {
        for (const Bus& bus : data.buses) {
            if (retained_ids.find(bus.id) == retained_ids.end()) {
                external_ids.insert(bus.id);
            }
        }
    }
    if (external_ids.empty()) {
        summary.retained_buses = static_cast<int>(data.buses.size());
        return summary;
    }

    if (use_default_ward_selection) {
        std::map<int, std::vector<int>> external_neighbors;
        std::vector<int> boundary_external_seeds;
        for (const Branch& branch : data.branches) {
            const bool from_external = external_ids.find(branch.from) != external_ids.end();
            const bool to_external = external_ids.find(branch.to) != external_ids.end();
            if (from_external && to_external) {
                external_neighbors[branch.from].push_back(branch.to);
                external_neighbors[branch.to].push_back(branch.from);
            } else if (from_external != to_external) {
                boundary_external_seeds.push_back(from_external ? branch.from : branch.to);
            }
        }

        std::set<int> reachable_external_ids;
        std::vector<int> pending = boundary_external_seeds;
        while (!pending.empty()) {
            const int bus_id = pending.back();
            pending.pop_back();
            if (!reachable_external_ids.insert(bus_id).second) {
                continue;
            }
            const auto neighbors_it = external_neighbors.find(bus_id);
            if (neighbors_it == external_neighbors.end()) {
                continue;
            }
            for (int neighbor : neighbors_it->second) {
                if (reachable_external_ids.find(neighbor) == reachable_external_ids.end()) {
                    pending.push_back(neighbor);
                }
            }
        }
        external_ids = reachable_external_ids;
        if (external_ids.empty()) {
            summary.retained_buses = static_cast<int>(data.buses.size());
            return summary;
        }
    }

    std::set<int> boundary_ids;
    for (const Branch& branch : data.branches) {
        const bool from_external = external_ids.find(branch.from) != external_ids.end();
        const bool to_external = external_ids.find(branch.to) != external_ids.end();
        if (from_external == to_external) {
            continue;
        }
        boundary_ids.insert(from_external ? branch.to : branch.from);
    }

    std::map<int, std::complex<double>> boundary_injection_mva;
    for (const Branch& branch : data.branches) {
        const bool from_external = external_ids.find(branch.from) != external_ids.end();
        const bool to_external = external_ids.find(branch.to) != external_ids.end();
        if (from_external == to_external) {
            continue;
        }
        const Bus& from_bus = data.buses[static_cast<std::size_t>(bus_position[branch.from])];
        const Bus& to_bus = data.buses[static_cast<std::size_t>(bus_position[branch.to])];
        if (from_external) {
            boundary_injection_mva[branch.to] += branch_power_from_end(branch, to_bus, from_bus, data.base_mva);
        } else {
            boundary_injection_mva[branch.from] += branch_power_from_end(branch, from_bus, to_bus, data.base_mva);
        }
    }

    std::vector<Branch> added_branches;
    std::map<int, std::complex<double>> added_shunts;
    if (options.method == EquivalentReductionMethod::Ward && !boundary_ids.empty()) {
        std::vector<int> boundary(boundary_ids.begin(), boundary_ids.end());
        std::vector<int> external(external_ids.begin(), external_ids.end());
        std::map<int, int> boundary_index;
        std::map<int, int> external_index;
        for (std::size_t i = 0; i < boundary.size(); ++i) {
            boundary_index[boundary[i]] = static_cast<int>(i);
        }
        for (std::size_t i = 0; i < external.size(); ++i) {
            external_index[external[i]] = static_cast<int>(i);
        }

        const int nb = static_cast<int>(boundary.size());
        const int ne = static_cast<int>(external.size());
        std::vector<std::vector<std::complex<double>>> ybb = make_matrix(nb, nb);
        std::vector<std::vector<std::complex<double>>> yee = make_matrix(ne, ne);
        std::vector<std::vector<std::complex<double>>> yeb = make_matrix(ne, nb);
        std::vector<std::vector<std::complex<double>>> ybe = make_matrix(nb, ne);
        std::vector<std::vector<std::complex<double>>> ysub = make_matrix(nb + ne, nb + ne);
        std::map<int, int> sub_index;
        for (int i = 0; i < nb; ++i) {
            sub_index[boundary[static_cast<std::size_t>(i)]] = i;
        }
        for (int i = 0; i < ne; ++i) {
            sub_index[external[static_cast<std::size_t>(i)]] = nb + i;
        }
        for (const Branch& branch : data.branches) {
            const bool from_external = external_ids.find(branch.from) != external_ids.end();
            const bool to_external = external_ids.find(branch.to) != external_ids.end();
            if (!from_external && !to_external) {
                continue;
            }
            const auto from_it = sub_index.find(branch.from);
            const auto to_it = sub_index.find(branch.to);
            if (from_it == sub_index.end() || to_it == sub_index.end()) {
                continue;
            }
            add_series_only_branch_to_matrix(branch, from_it->second, to_it->second, ysub);
        }
        for (int row = 0; row < nb; ++row) {
            for (int col = 0; col < nb; ++col) {
                ybb[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)] = ysub[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)];
            }
        }
        for (int row = 0; row < ne; ++row) {
            for (int col = 0; col < ne; ++col) {
                yee[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)] = ysub[static_cast<std::size_t>(nb + row)][static_cast<std::size_t>(nb + col)];
            }
            for (int col = 0; col < nb; ++col) {
                yeb[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)] = ysub[static_cast<std::size_t>(nb + row)][static_cast<std::size_t>(col)];
                ybe[static_cast<std::size_t>(col)][static_cast<std::size_t>(row)] = ysub[static_cast<std::size_t>(col)][static_cast<std::size_t>(nb + row)];
            }
        }
        const auto solved = solve_complex_linear_system(yee, yeb);
        std::vector<std::vector<std::complex<double>>> yward = ybb;
        for (int i = 0; i < nb; ++i) {
            for (int j = 0; j < nb; ++j) {
                for (int k = 0; k < ne; ++k) {
                    yward[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] -=
                        ybe[static_cast<std::size_t>(i)][static_cast<std::size_t>(k)] * solved[static_cast<std::size_t>(k)][static_cast<std::size_t>(j)];
                }
            }
        }
        for (int i = 0; i < nb; ++i) {
            for (int j = i + 1; j < nb; ++j) {
                const std::complex<double> y = -yward[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)];
                if (std::abs(y) <= TOLERANCE) {
                    continue;
                }
                const std::complex<double> z = 1.0 / y;
                if (options.zmax > 0.0 && std::abs(z) > options.zmax) {
                    continue;
                }
                Branch equivalent;
                equivalent.from = boundary[static_cast<std::size_t>(i)];
                equivalent.to = boundary[static_cast<std::size_t>(j)];
                equivalent.circuit = 900000 + static_cast<int>(added_branches.size());
                equivalent.r = z.real();
                equivalent.x = z.imag();
                equivalent.b = 0.0;
                equivalent.tap = 1.0;
                equivalent.rate_mva = 1.0e6;
                added_branches.push_back(equivalent);
                yward[static_cast<std::size_t>(i)][static_cast<std::size_t>(i)] -= y;
                yward[static_cast<std::size_t>(j)][static_cast<std::size_t>(j)] -= y;
            }
        }
        for (int i = 0; i < nb; ++i) {
            const std::complex<double> y = yward[static_cast<std::size_t>(i)][static_cast<std::size_t>(i)];
            if (std::abs(y) > TOLERANCE) {
                added_shunts[boundary[static_cast<std::size_t>(i)]] += y;
            }
        }
    }

    for (Bus& bus : data.buses) {
        const auto injection_it = boundary_injection_mva.find(bus.id);
        if (injection_it != boundary_injection_mva.end()) {
            bus.pl_mw += injection_it->second.real();
            bus.ql_mvar += injection_it->second.imag();
        }
        const auto shunt_it = added_shunts.find(bus.id);
        if (shunt_it != added_shunts.end()) {
            bus.gsh += shunt_it->second.real();
            bus.bsh += shunt_it->second.imag();
        }
    }

    const int original_branch_count = static_cast<int>(data.branches.size());
    data.branches.erase(std::remove_if(data.branches.begin(), data.branches.end(), [&](const Branch& branch) {
        return external_ids.find(branch.from) != external_ids.end() || external_ids.find(branch.to) != external_ids.end();
    }), data.branches.end());
    summary.removed_branches = original_branch_count - static_cast<int>(data.branches.size());
    data.branches.insert(data.branches.end(), added_branches.begin(), added_branches.end());

    data.buses.erase(std::remove_if(data.buses.begin(), data.buses.end(), [&](const Bus& bus) {
        return external_ids.find(bus.id) != external_ids.end();
    }), data.buses.end());
    for (OriginalBusRecord& original_bus : data.original_buses) {
        if (external_ids.find(original_bus.bus.id) != external_ids.end()) {
            original_bus.collapsed = true;
            original_bus.representative_bus = 0;
        }
    }
    remove_missing_device_records(data);

    summary.retained_buses = static_cast<int>(data.buses.size());
    summary.external_buses = static_cast<int>(external_ids.size());
    summary.boundary_buses = static_cast<int>(boundary_ids.size());
    summary.added_branches = static_cast<int>(added_branches.size());
    summary.added_shunts = static_cast<int>(added_shunts.size());
    summary.applied = true;
    return summary;
}
