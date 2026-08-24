cmake_minimum_required(VERSION 3.20)

project(o_grid_power_flow LANGUAGES CXX)

set(O_GRID_EIGEN_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../.native-deps/eigen" CACHE PATH "Eigen include root")
if(EXISTS "${O_GRID_EIGEN_ROOT}/Eigen/SparseLU")
    message(STATUS "Using Eigen headers from ${O_GRID_EIGEN_ROOT}")
endif()

set(O_GRID_CPP_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(O_GRID_CPP_UTILS
    utils/branch_flow.cpp
    utils/case_data.cpp
    utils/definitions.cpp
    utils/excel_export.cpp
    utils/linear_solver.cpp
    utils/network_reduction.cpp
    utils/reporting.cpp
    utils/ybus.cpp
)
set(O_GRID_CPP_MODELS
    models/csc.cpp
    models/lcc.cpp
    models/ltc.cpp
    models/pst.cpp
    models/shunt.cpp
    models/svc.cpp
)

add_library(o_grid_power_flow STATIC ${O_GRID_CPP_UTILS} ${O_GRID_CPP_MODELS} newton_raphson.cpp fast_decoupled.cpp)
target_compile_features(o_grid_power_flow PUBLIC cxx_std_17)
target_compile_definitions(o_grid_power_flow PRIVATE
    POWER_SIMULATOR_NEWTON_LIBRARY
    POWER_SIMULATOR_FAST_DECOUPLED_LIBRARY
)
target_include_directories(o_grid_power_flow PUBLIC "${O_GRID_CPP_INCLUDE_DIR}")
target_include_directories(o_grid_power_flow SYSTEM PUBLIC "${O_GRID_EIGEN_ROOT}")

add_executable(o_grid_newton newton_raphson.cpp ${O_GRID_CPP_UTILS} ${O_GRID_CPP_MODELS})
target_compile_features(o_grid_newton PRIVATE cxx_std_17)
target_include_directories(o_grid_newton PRIVATE "${O_GRID_CPP_INCLUDE_DIR}")
target_include_directories(o_grid_newton SYSTEM PRIVATE "${O_GRID_EIGEN_ROOT}")

add_executable(o_grid_fast_decoupled fast_decoupled.cpp newton_raphson.cpp ${O_GRID_CPP_UTILS} ${O_GRID_CPP_MODELS})
target_compile_features(o_grid_fast_decoupled PRIVATE cxx_std_17)
target_compile_definitions(o_grid_fast_decoupled PRIVATE POWER_SIMULATOR_NEWTON_LIBRARY)
target_include_directories(o_grid_fast_decoupled PRIVATE "${O_GRID_CPP_INCLUDE_DIR}")
target_include_directories(o_grid_fast_decoupled SYSTEM PRIVATE "${O_GRID_EIGEN_ROOT}")