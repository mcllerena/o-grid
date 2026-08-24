#include "../headers/utils/linear_solver.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#if __has_include(<Eigen/SparseLU>)
#include <Eigen/SparseLU>
#define O_GRID_HAS_EIGEN 1
#else
#define O_GRID_HAS_EIGEN 0
#endif

std::vector<double> solve_linear_system(std::vector<std::vector<double>> a, std::vector<double> b) {
    const std::size_t n = b.size();
    for (std::size_t col = 0; col < n; ++col) {
        std::size_t pivot = col;
        double max_abs = std::abs(a[col][col]);
        for (std::size_t row = col + 1; row < n; ++row) {
            const double value = std::abs(a[row][col]);
            if (value > max_abs) {
                max_abs = value;
                pivot = row;
            }
        }

        if (max_abs < 1e-14) {
            throw std::runtime_error("Newton Jacobian is singular or ill-conditioned");
        }

        if (pivot != col) {
            std::swap(a[pivot], a[col]);
            std::swap(b[pivot], b[col]);
        }

        const double diag = a[col][col];
        for (std::size_t row = col + 1; row < n; ++row) {
            const double factor = a[row][col] / diag;
            if (factor == 0.0) {
                continue;
            }
            a[row][col] = 0.0;
            for (std::size_t k = col + 1; k < n; ++k) {
                a[row][k] -= factor * a[col][k];
            }
            b[row] -= factor * b[col];
        }
    }

    std::vector<double> x(n);
    for (std::size_t row = n; row-- > 0;) {
        double rhs = b[row];
        for (std::size_t col = row + 1; col < n; ++col) {
            rhs -= a[row][col] * x[col];
        }
        x[row] = rhs / a[row][row];
    }
    return x;
}

namespace {

void sparse_matvec(const SparseRealMatrix& matrix, const std::vector<double>& x, std::vector<double>& y) {
    y.assign(matrix.size, 0.0);
    for (int row = 0; row < matrix.size; ++row) {
        double value = 0.0;
        for (const auto& entry : matrix.rows[row]) {
            value += entry.second * x[entry.first];
        }
        y[row] = value;
    }
}

double dot_product(const std::vector<double>& a, const std::vector<double>& b) {
    double value = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        value += a[i] * b[i];
    }
    return value;
}

double infinity_norm(const std::vector<double>& values) {
    double result = 0.0;
    for (double value : values) {
        result = std::max(result, std::abs(value));
    }
    return result;
}

} // namespace

std::vector<double> solve_bicgstab(const SparseRealMatrix& matrix,
                                   const std::vector<double>& b,
                                   double tolerance,
                                   int max_iterations) {
    const int n = matrix.size;
    std::vector<double> x(n, 0.0);
    std::vector<double> r = b;
    std::vector<double> r_hat = r;
    std::vector<double> p(n, 0.0);
    std::vector<double> v(n, 0.0);
    std::vector<double> s(n, 0.0);
    std::vector<double> t(n, 0.0);
    std::vector<double> phat(n, 0.0);
    std::vector<double> shat(n, 0.0);
    std::vector<double> diagonal(n, 1.0);

    for (int row = 0; row < n; ++row) {
        for (const auto& entry : matrix.rows[row]) {
            if (entry.first == row && std::abs(entry.second) > 1e-14) {
                diagonal[row] = entry.second;
                break;
            }
        }
    }

    const double rhs_norm = std::max(infinity_norm(b), 1.0);
    double rho_old = 1.0;
    double alpha = 1.0;
    double omega = 1.0;

    for (int iteration = 0; iteration < max_iterations; ++iteration) {
        const double rho_new = dot_product(r_hat, r);
        if (std::abs(rho_new) < 1e-30) {
            throw std::runtime_error("BiCGSTAB breakdown: rho is near zero");
        }

        if (iteration == 0) {
            p = r;
        } else {
            const double beta = (rho_new / rho_old) * (alpha / omega);
            for (int i = 0; i < n; ++i) {
                p[i] = r[i] + beta * (p[i] - omega * v[i]);
            }
        }

        for (int i = 0; i < n; ++i) {
            phat[i] = p[i] / diagonal[i];
        }
        sparse_matvec(matrix, phat, v);
        const double denom = dot_product(r_hat, v);
        if (std::abs(denom) < 1e-30) {
            throw std::runtime_error("BiCGSTAB breakdown: alpha denominator is near zero");
        }
        alpha = rho_new / denom;

        for (int i = 0; i < n; ++i) {
            s[i] = r[i] - alpha * v[i];
        }
        if (infinity_norm(s) <= tolerance * rhs_norm) {
            for (int i = 0; i < n; ++i) {
                x[i] += alpha * phat[i];
            }
            return x;
        }

        for (int i = 0; i < n; ++i) {
            shat[i] = s[i] / diagonal[i];
        }
        sparse_matvec(matrix, shat, t);
        const double tt = dot_product(t, t);
        if (std::abs(tt) < 1e-30) {
            throw std::runtime_error("BiCGSTAB breakdown: omega denominator is near zero");
        }
        omega = dot_product(t, s) / tt;
        if (std::abs(omega) < 1e-30) {
            throw std::runtime_error("BiCGSTAB breakdown: omega is near zero");
        }

        for (int i = 0; i < n; ++i) {
            x[i] += alpha * phat[i] + omega * shat[i];
            r[i] = s[i] - omega * t[i];
        }
        if (infinity_norm(r) <= tolerance * rhs_norm) {
            return x;
        }
        rho_old = rho_new;
    }

    throw std::runtime_error("BiCGSTAB did not converge within the linear iteration limit");
}

std::vector<double> solve_sparse_lu(const SparseRealMatrix& matrix, const std::vector<double>& b) {
#if O_GRID_HAS_EIGEN
    using EigenSparseMatrix = Eigen::SparseMatrix<double, Eigen::ColMajor, int>;
    std::vector<Eigen::Triplet<double>> triplets;
    std::size_t nnz = 0;
    for (const auto& row : matrix.rows) {
        nnz += row.size();
    }
    triplets.reserve(nnz);

    for (int row = 0; row < matrix.size; ++row) {
        for (const auto& entry : matrix.rows[row]) {
            triplets.emplace_back(row, entry.first, entry.second);
        }
    }

    EigenSparseMatrix eigen_matrix(matrix.size, matrix.size);
    eigen_matrix.setFromTriplets(triplets.begin(), triplets.end());
    eigen_matrix.makeCompressed();

    Eigen::VectorXd rhs(matrix.size);
    for (int i = 0; i < matrix.size; ++i) {
        rhs[i] = b[i];
    }

    Eigen::SparseLU<EigenSparseMatrix, Eigen::COLAMDOrdering<int>> solver;
    solver.compute(eigen_matrix);
    if (solver.info() != Eigen::Success) {
        throw std::runtime_error("Eigen SparseLU factorization failed: " + std::string(solver.lastErrorMessage()));
    }
    const Eigen::VectorXd solution = solver.solve(rhs);
    if (solver.info() != Eigen::Success) {
        throw std::runtime_error("Eigen SparseLU solve failed");
    }

    std::vector<double> x(matrix.size);
    for (int i = 0; i < matrix.size; ++i) {
        x[i] = solution[i];
    }
    return x;
#else
    return solve_bicgstab(matrix, b, 1.0e-10, std::max(2000, matrix.size * 2));
#endif
}
