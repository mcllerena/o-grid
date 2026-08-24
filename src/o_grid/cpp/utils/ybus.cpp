#include "../headers/utils/ybus.h"

#include <cmath>
#include <map>
#include <stdexcept>

#include "../headers/models/csc.h"

std::vector<std::vector<std::complex<double>>> build_ybus(const CaseData& data) {
    const std::size_t n = data.buses.size();
    std::vector<std::vector<std::complex<double>>> ybus(n, std::vector<std::complex<double>>(n));
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < n; ++i) {
        bus_index[data.buses[i].id] = i;
    }

    const std::vector<CscState> csc_states = build_csc_states(data);
    std::map<int, double> csc_x_by_branch;
    for (const CscState& state : csc_states) {
        if (state.active && state.branch_index >= 0) {
            csc_x_by_branch[state.branch_index] += state.x_pu;
        }
    }

    for (std::size_t branch_index = 0; branch_index < data.branches.size(); ++branch_index) {
        const Branch& branch = data.branches[branch_index];
        const auto from_it = bus_index.find(branch.from);
        const auto to_it = bus_index.find(branch.to);
        if (from_it == bus_index.end() || to_it == bus_index.end()) {
            throw std::runtime_error("Branch references an unknown bus");
        }

        const std::size_t f = from_it->second;
        const std::size_t t = to_it->second;
        const auto csc_it = csc_x_by_branch.find(static_cast<int>(branch_index));
        const double effective_x = branch.x + (csc_it != csc_x_by_branch.end() ? csc_it->second : 0.0);
        const std::complex<double> z(branch.r, effective_x);
        if (std::abs(z) < TOLERANCE) {
            throw std::runtime_error("Branch has near-zero impedance");
        }

        const std::complex<double> y = 1.0 / z;
        const std::complex<double> charging(0.0, branch.b / 2.0);
        const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);

        ybus[f][f] += (y + charging) / (tap * std::conj(tap));
        ybus[t][t] += y + charging;
        ybus[f][t] -= y / std::conj(tap);
        ybus[t][f] -= y / tap;
    }

    add_csc_to_ybus(ybus, csc_states);

    for (std::size_t i = 0; i < n; ++i) {
        ybus[i][i] += std::complex<double>(data.buses[i].gsh, data.buses[i].bsh);
    }

    return ybus;
}

SparseYbus build_sparse_ybus(const CaseData& data) {
    const std::size_t n = data.buses.size();
    std::map<int, std::size_t> bus_index;
    for (std::size_t i = 0; i < n; ++i) {
        bus_index[data.buses[i].id] = i;
    }

    std::vector<std::map<int, std::complex<double>>> yrows(n);
    const std::vector<CscState> csc_states = build_csc_states(data);
    std::map<int, double> csc_x_by_branch;
    for (const CscState& state : csc_states) {
        if (state.active && state.branch_index >= 0) {
            csc_x_by_branch[state.branch_index] += state.x_pu;
        }
    }

    for (std::size_t branch_index = 0; branch_index < data.branches.size(); ++branch_index) {
        const Branch& branch = data.branches[branch_index];
        const auto from_it = bus_index.find(branch.from);
        const auto to_it = bus_index.find(branch.to);
        if (from_it == bus_index.end() || to_it == bus_index.end()) {
            throw std::runtime_error("Branch references an unknown bus");
        }

        const int f = static_cast<int>(from_it->second);
        const int t = static_cast<int>(to_it->second);
        const auto csc_it = csc_x_by_branch.find(static_cast<int>(branch_index));
        const double effective_x = branch.x + (csc_it != csc_x_by_branch.end() ? csc_it->second : 0.0);
        const std::complex<double> z(branch.r, effective_x);
        if (std::abs(z) < TOLERANCE) {
            throw std::runtime_error("Branch has near-zero impedance");
        }

        const std::complex<double> y = 1.0 / z;
        const std::complex<double> charging(0.0, branch.b / 2.0);
        const std::complex<double> tap = std::polar(branch.tap, branch.phase_rad);

        yrows[f][f] += (y + charging) / (tap * std::conj(tap));
        yrows[t][t] += y + charging;
        yrows[f][t] -= y / std::conj(tap);
        yrows[t][f] -= y / tap;
    }

    for (const CscState& state : csc_states) {
        if (!state.active || state.branch_index >= 0) {
            continue;
        }
        const std::complex<double> y = 1.0 / std::complex<double>(0.0, state.x_pu);
        yrows[state.from_index][state.from_index] += y;
        yrows[state.to_index][state.to_index] += y;
        yrows[state.from_index][state.to_index] -= y;
        yrows[state.to_index][state.from_index] -= y;
    }

    for (std::size_t i = 0; i < n; ++i) {
        yrows[i][static_cast<int>(i)] += std::complex<double>(data.buses[i].gsh, data.buses[i].bsh);
    }

    SparseYbus ybus;
    ybus.rows.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        ybus.rows[i].reserve(yrows[i].size());
        for (const auto& entry : yrows[i]) {
            if (std::abs(entry.second) > 0.0) {
                ybus.rows[i].push_back({entry.first, entry.second});
            }
        }
    }
    return ybus;
}

void calculate_power(const std::vector<std::vector<std::complex<double>>>& ybus,
                     const std::vector<double>& vm,
                     const std::vector<double>& va,
                     std::vector<double>& p,
                     std::vector<double>& q) {
    const std::size_t n = vm.size();
    p.assign(n, 0.0);
    q.assign(n, 0.0);

    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) {
            const double g = ybus[i][j].real();
            const double b = ybus[i][j].imag();
            const double angle = va[i] - va[j];
            p[i] += vm[i] * vm[j] * (g * std::cos(angle) + b * std::sin(angle));
            q[i] += vm[i] * vm[j] * (g * std::sin(angle) - b * std::cos(angle));
        }
    }
}

void calculate_power_sparse(const SparseYbus& ybus,
                            const std::vector<double>& vm,
                            const std::vector<double>& va,
                            std::vector<double>& p,
                            std::vector<double>& q) {
    const std::size_t n = vm.size();
    p.assign(n, 0.0);
    q.assign(n, 0.0);

    for (std::size_t i = 0; i < n; ++i) {
        for (const SparseComplexEntry& entry : ybus.rows[i]) {
            const int j = entry.col;
            const double g = entry.value.real();
            const double b = entry.value.imag();
            const double angle = va[i] - va[j];
            p[i] += vm[i] * vm[j] * (g * std::cos(angle) + b * std::sin(angle));
            q[i] += vm[i] * vm[j] * (g * std::sin(angle) - b * std::cos(angle));
        }
    }
}
