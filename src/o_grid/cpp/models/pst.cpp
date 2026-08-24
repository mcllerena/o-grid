#include "../headers/models/pst.h"

#include <cmath>

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

} // namespace

void apply_pst_to_branches(CaseData& data) {
    for (Pst& pst : data.psts) {
        pst.branch_index = find_branch_index(data.branches, pst.from, pst.to, pst.circuit);
        if (pst.branch_index < 0) {
            continue;
        }
        Branch& branch = data.branches[static_cast<std::size_t>(pst.branch_index)];
        if (std::abs(pst.r) > 0.0 || std::abs(pst.x) > 0.0) {
            branch.r = pst.r;
            branch.x = pst.x;
        }
        branch.phase_rad = pst.phase_rad;
    }
}
