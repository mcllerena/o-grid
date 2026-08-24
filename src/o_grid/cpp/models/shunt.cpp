#include "../headers/models/shunt.h"

#include <algorithm>
#include <cmath>

namespace {

std::map<int, std::size_t> make_bus_index(const CaseData& data) {
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < data.buses.size(); ++i) {
        bus_index[data.buses[i].id] = i;
    }
    return bus_index;
}

void add_bus_shunt(CaseData& data, const std::map<int, std::size_t>& bus_index, int bus_id, double q_mvar) {
    if (std::abs(q_mvar) < TOLERANCE) {
        return;
    }
    const auto it = bus_index.find(bus_id);
    if (it != bus_index.end()) {
        data.buses[it->second].bsh += q_mvar / data.base_mva;
    }
}

} // namespace

void apply_parsed_shunts_to_buses(CaseData& data, const std::map<int, BusShuntBankAggregate>& bus_shunt_bank_totals) {
    const std::map<int, std::size_t> bus_index = make_bus_index(data);
    for (std::size_t i = 0; i < data.bus_shunts.size(); ++i) {
        BusShunt& shunt = data.bus_shunts[i];
        const auto bank_total_it = bus_shunt_bank_totals.find(static_cast<int>(i + 1));
        const double q_mvar = bank_total_it != bus_shunt_bank_totals.end() ? bank_total_it->second.initial_mvar : shunt.q_mvar;
        shunt.applied_q_mvar = q_mvar;
        if (bank_total_it != bus_shunt_bank_totals.end()) {
            shunt.qmin_mvar = bank_total_it->second.min_mvar;
            shunt.qmax_mvar = bank_total_it->second.max_mvar;
        } else {
            shunt.qmin_mvar = std::min(0.0, q_mvar);
            shunt.qmax_mvar = std::max(0.0, q_mvar);
        }
        add_bus_shunt(data, bus_index, shunt.bus, q_mvar);
    }
    for (const LineShunt& shunt : data.line_shunts) {
        add_bus_shunt(data, bus_index, shunt.from, shunt.q_from_mvar);
        add_bus_shunt(data, bus_index, shunt.to, shunt.q_to_mvar);
    }
}

bool adjust_switched_bus_shunts(CaseData& data, const PowerFlowResult& result) {
    const std::map<int, std::size_t> bus_index = make_bus_index(data);
    bool changed = false;
    constexpr double voltage_deadband = 1e-3;
    constexpr double q_deadband_mvar = 1e-3;

    for (BusShunt& shunt : data.bus_shunts) {
        if (shunt.vmax <= shunt.vmin || std::abs(shunt.qmax_mvar - shunt.qmin_mvar) < q_deadband_mvar) {
            continue;
        }
        const int controlled_bus = shunt.remote_bus != 0 ? shunt.remote_bus : shunt.bus;
        const auto control_it = bus_index.find(controlled_bus);
        const auto device_it = bus_index.find(shunt.bus);
        if (control_it == bus_index.end() || device_it == bus_index.end() || control_it->second >= result.vm.size()) {
            continue;
        }

        const double controlled_vm = result.vm[control_it->second];
        double target_q_mvar = shunt.applied_q_mvar;
        if (controlled_vm > shunt.vmax + voltage_deadband) {
            target_q_mvar = shunt.qmin_mvar < 0.0 ? shunt.qmin_mvar : 0.0;
        } else if (controlled_vm < shunt.vmin - voltage_deadband) {
            target_q_mvar = shunt.qmax_mvar > 0.0 ? shunt.qmax_mvar : 0.0;
        }

        const double delta_q_mvar = target_q_mvar - shunt.applied_q_mvar;
        if (std::abs(delta_q_mvar) < q_deadband_mvar) {
            continue;
        }
        data.buses[device_it->second].bsh += delta_q_mvar / data.base_mva;
        shunt.applied_q_mvar = target_q_mvar;
        changed = true;
    }
    return changed;
}
