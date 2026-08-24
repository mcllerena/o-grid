#pragma once

#include <vector>

#include "power_flow_types.h"

std::vector<double> solve_linear_system(std::vector<std::vector<double>> a, std::vector<double> b);

std::vector<double> solve_bicgstab(const SparseRealMatrix& matrix,
                                   const std::vector<double>& b,
                                   double tolerance,
                                   int max_iterations);

std::vector<double> solve_sparse_lu(const SparseRealMatrix& matrix, const std::vector<double>& b);
