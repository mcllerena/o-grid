#pragma once

#include <complex>
#include <vector>

#include "../case_data.h"
#include "power_flow_types.h"

std::vector<std::vector<std::complex<double>>> build_ybus(const CaseData& data);
SparseYbus build_sparse_ybus(const CaseData& data);

void calculate_power(const std::vector<std::vector<std::complex<double>>>& ybus,
                     const std::vector<double>& vm,
                     const std::vector<double>& va,
                     std::vector<double>& p,
                     std::vector<double>& q);

void calculate_power_sparse(const SparseYbus& ybus,
                            const std::vector<double>& vm,
                            const std::vector<double>& va,
                            std::vector<double>& p,
                            std::vector<double>& q);
