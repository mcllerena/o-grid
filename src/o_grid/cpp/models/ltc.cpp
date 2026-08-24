#include "../headers/models/ltc.h"

#include <algorithm>
#include <cmath>
#include <map>

namespace {

int find_branch_index(const std::vector<Branch>& branches, int from, int to, int circuit) {
    for (std::size_t i = 0; i < branches.size(); ++i) {
        const Branch& branch = branches[i];
        if (branch.from == from && branch.to == to && branch.circuit == circuit) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

std::map<int, std::size_t> make_bus_index(const CaseData& data) {
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
    }
    return bus_index;
}

} // namespace

void apply_ltc_to_branches(CaseData& data) {
    for (Ltc& ltc : data.ltcs) {
        ltc.branch_index = find_branch_index(data.branches, ltc.from, ltc.to, ltc.circuit);
        if (ltc.branch_index < 0) {
            continue;
        }
        Branch& branch = data.branches[static_cast<std::size_t>(ltc.branch_index)];
        if (std::abs(ltc.r) > 0.0 || std::abs(ltc.x) > 0.0) {
            branch.r = ltc.r;
            branch.x = ltc.x;
        }
        if (std::abs(ltc.tap) > TOLERANCE) {
            branch.tap = ltc.tap;
        }
        branch.tap_min = ltc.tap_min;
        branch.tap_max = ltc.tap_max;
    }
}

bool adjust_ltc_taps(CaseData& data, const PowerFlowResult& result) {
    const std::map<int, std::size_t> bus_index = make_bus_index(data);
    bool changed = false;
    constexpr double voltage_deadband = 1e-3;
    const double tap_deadband = MIN_DENOMINATOR;

    for (Ltc& ltc : data.ltcs) {
        if (!ltc.voltage_control || ltc.branch_index < 0 || ltc.tap_min <= 0.0 || ltc.tap_max <= ltc.tap_min) {
            continue;
        }
        const auto control_it = bus_index.find(ltc.control_bus);
        if (control_it == bus_index.end() || control_it->second >= result.vm.size()) {
            continue;
        }
        const double voltage_error = ltc.v_target - result.vm[control_it->second];
        if (std::abs(voltage_error) < voltage_deadband) {
            continue;
        }

        const double direction = ltc.control_bus == ltc.from ? 1.0 : -1.0;
        const double limited_step = std::max(-0.01, std::min(0.01, direction * 0.5 * voltage_error));
        const double next_tap = std::max(ltc.tap_min, std::min(ltc.tap_max, ltc.tap + limited_step));
        if (std::abs(next_tap - ltc.tap) < tap_deadband) {
            continue;
        }

        ltc.tap = next_tap;
        data.branches[static_cast<std::size_t>(ltc.branch_index)].tap = next_tap;
        changed = true;
    }
    return changed;
}
